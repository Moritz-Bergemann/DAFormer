# Obtained from: https://github.com/NVlabs/SegFormer
# Modifications: Model construction with loop
# ---------------------------------------------------------------
# Copyright (c) 2021, NVIDIA Corporation. All rights reserved.
#
# This work is licensed under the NVIDIA Source Code License
# ---------------------------------------------------------------
# A copy of the license is available at resources/license_segformer

import torch
import torch.nn as nn
from mmcv.cnn import ConvModule

from mmseg.ops import resize
from ..builder import HEADS
from .decode_head import BaseDecodeHead


# M-TODO this should probably go somewhere else
class GradientReversalFunction(Function):
    """Gradient reversal function. Acts as identity transform during forward pass, 
    but multiplies gradient by -alpha during backpropagation. this means alpha 
    effectively becomes the loss weight during training.
    """
    @staticmethod
    def forward(ctx, x, alpha):
        ctx.save_for_backward(x, alpha)
        return x
    
    @staticmethod
    def backward(ctx, grad_output):
        grad_input = None
        _, alpha = ctx.saved_tensors
        if ctx.needs_input_grad[0]:
            grad_input = - alpha*grad_output
        return grad_input, None

revgrad = GradientReversalFunction.apply

class GradientReversal(nn.Module):
    def __init__(self, alpha=torch.tensor([1.])):
        super().__init__()
        self.alpha = torch.tensor(alpha, requires_grad=False)

    def forward(self, x):
        return revgrad(x, self.alpha)

## END GRADIENT REVERSAL ##

# M-TODO also put this somewhere else
from mmcv.runner import BaseModule
class AdversarialDiscriminator(BaseModule):
    @staticmethod
    def build_discriminator(cfg): # M-TODO consider making this part of the module registration system in MMCV, would eventually call MODELS.build() or something like that (like UDA itself)
        return AdversarialDiscriminator(**cfg)

    def __init__(self, in_features, hidden_features, init_cfg=None, classes=2): # I think actual weight initialisation will happen in base_module.py??
        super(AdversarialDiscriminator, self).__init__(init_cfg)

        # M-TODO use weights (because we're gonna need to pretrain this guy anyway) - NOTE: I think just passing in init_cfg into __init__ does this
        # M-TODO does this get put on GPU automatically?

        self.grad_rev = GradientReversal()
        self.flatten = nn.Flatten()
        self.lin1 = nn.Linear(in_features, hidden_features) # M-TODO figure out shape of segformer output
        self.rel1 = nn.ReLU()
        self.lin2 = nn.Linear(hidden_features, 2)

        self.loss = nn.CrossEntropyLoss()

    # M-TODO random weight initialisation in a defined manner? rather than just using the defaults

    def forward(self, x):
        x = self.grad_rev(x)
        
        x = self.flatten(x)
        x = self.lin1(x)
        x = self.rel1(x)
        x = self.lin2(x)

        return x # M-TODO will likely need adjustment
    
    def forward_train(self, img, labels):
        pred = self(img)

        loss = self.loss(pred, labels)

        log_vars = dict() # M-TODO logging etc here

        return loss, log_vars

class MLP(nn.Module):
    """Linear Embedding."""

    def __init__(self, input_dim=2048, embed_dim=768):
        super().__init__()
        self.proj = nn.Linear(input_dim, embed_dim)

    def forward(self, x):
        x = x.flatten(2).transpose(1, 2).contiguous() # M-TODO: Figure out why they do flatten then transpose then contiguous?
        x = self.proj(x)
        return x


@HEADS.register_module()
class SegFormerHead(BaseDecodeHead):
    """
    SegFormer: Simple and Efficient Design for Semantic Segmentation with
    Transformers
    """

    def __init__(self, **kwargs):
        super(SegFormerHead, self).__init__(
            input_transform='multiple_select', **kwargs)

        decoder_params = kwargs['decoder_params']
        embedding_dim = decoder_params['embed_dim']
        conv_kernel_size = decoder_params['conv_kernel_size']

        self.linear_c = {} # M: Build linear decoder channels
        for i, in_channels in zip(self.in_index, self.in_channels): # M: in_index is superclass param, index position(s) of features to do
            self.linear_c[str(i)] = MLP(
                input_dim=in_channels, embed_dim=embedding_dim) # M: input_dim is input shape, embed_dim output shape
        self.linear_c = nn.ModuleDict(self.linear_c)

        self.linear_fuse = ConvModule( # M: Fuses all features of linear decoder together
            in_channels=embedding_dim * len(self.in_index),
            out_channels=embedding_dim,
            kernel_size=conv_kernel_size,
            padding=0 if conv_kernel_size == 1 else conv_kernel_size // 2,
            norm_cfg=kwargs['norm_cfg'])

        self.linear_pred = nn.Conv2d(
            embedding_dim, self.num_classes, kernel_size=1)

        self.discriminator = AdversarialDiscriminator(kwargs['adv_discriminator'])

    def forward(self, inputs):
        x = inputs
        n, _, h, w = x[-1].shape
        # for f in x:
        #     print(f.shape)

        _c = {}
        for i in self.in_index:
            # mmcv.print_log(f'{i}: {x[i].shape}, {self.linear_c[str(i)]}')
            _c[i] = self.linear_c[str(i)](x[i]).permute(0, 2, 1).contiguous() # M: Apply linear layer
            _c[i] = _c[i].reshape(n, -1, x[i].shape[2], x[i].shape[3])
            if i != 0:
                _c[i] = resize( # M: Upsample
                    _c[i],
                    size=x[0].size()[2:],
                    mode='bilinear',
                    align_corners=False)

        _c = self.linear_fuse(torch.cat(list(_c.values()), dim=1))

        if self.dropout is not None:
            x = self.dropout(_c)
        else:
            x = _c
        x = self.linear_pred(x)

        # Do domain prediction
        domain_pred = self.discriminator

        return x, domain_pred