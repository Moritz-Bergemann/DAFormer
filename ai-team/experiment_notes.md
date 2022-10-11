# Experiments
## General Repo Architecture Notes
[`UDADecorator`](mmseg/models/uda/uda_decorator.py) is a wrapper around a model for the performing of UDA.
[`DACS`](mmseg/models/uda/dacs.py) (Domain Adaptation via Cross-domain mixed Sampling) is a particular method for performing pseudolabelling-based UDA that was adapted for DAFormer in this repository.

### Common methods
`forward_train` is the method called by `BaseSegmentor` when `forward` (i.e. `__call__`) is called on it during training.

## General Setup
Install miniconda (on my Linux, I installed using the source sh script.)

Create a new conda environment (python 3.8)

```sh
conda create --name daformer python=3.8
```

Install pytorch
```sh
conda install pytorch torchvision torchaudio cudatoolkit=11.1 -c pytorch-lts -c nvidia
```

Install mmcv locally (mmsegmentation is in this repository, so does not need to be installed)
```sh
pip install -U openmim
mim install mmcv-full
```

## Experiment 1 - Domain Adversarial Loss
## Experiment 2 - Patch-wise Domain Adversarial Loss
## Experiment 3 - Patch-wise Domain Invariant Feature Encouragement (a la TVT)
## Experiemnt 3 - Patch-wise Feature Distances
## Experiment 4 - Cross-Attention

# A new network architecture