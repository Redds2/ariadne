import gin
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import CrossEntropyLoss
from ariadne.utils import one_hot_embedding
from torch.autograd import Variable
from typing import Optional

gin.external_configurable(CrossEntropyLoss)
@gin.configurable()
class TrackNetCrossEntropyLoss(nn.BCEWithLogitsLoss):
    def __init__(self,
                 weight=None,
                 size_average=None,
                 reduction: str = 'sum',
                 pos_weight=None):
        if weight:
            weight = torch.tensor(weight)
        if pos_weight:
            pos_weight = torch.tensor(pos_weight)

        super().__init__(weight=weight,
                     size_average=size_average,
                     reduction=reduction,
                     pos_weight=pos_weight)
    def forward(self, input, target):
        return super().forward(input, target.unsqueeze(-1).float())


@gin.configurable()
class FocalLoss(nn.Module):
    def __init__(self, alpha=1, gamma=2, logits=True, reduce=True):
        super(FocalLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.logits = logits
        self.reduce = reduce

    def forward(self, inputs, targets):
        targets = targets.float().unsqueeze(-1)
        if self.logits:
            BCE_loss = F.binary_cross_entropy_with_logits(inputs, targets, reduce=False)
        else:
            BCE_loss = F.binary_cross_entropy(inputs, targets, reduce=False)
        pt = torch.exp(-BCE_loss)
        F_loss = self.alpha * (1-pt)**self.gamma * BCE_loss
        if self.reduce:
            return torch.sum(F_loss)
        else:
            return F_loss