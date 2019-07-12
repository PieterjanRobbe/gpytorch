#!/usr/bin/env python3

import torch
from .kernel import Kernel
from ..lazy import KroneckerProductLazyTensor
from .polynomial_kernel import PolynomialKernel
from typing import Optional
from ..priors import Prior
from ..constraints import Positive, Interval


class PolynomialKernelGrad(PolynomialKernel):
    def forward(
        self,
        x1: torch.Tensor,
        x2: torch.Tensor,
        diag: Optional[bool] = False,
        last_dim_is_batch: Optional[bool] = False,
        **params
    ) -> torch.Tensor:
        offset = self.offset.view(*self.batch_shape, 1, 1)

        batch_shape = x1.shape[:-2]
        n1, d = x1.shape[-2:]
        n2 = x2.shape[-2]

        if diag:
            raise RuntimeError("None done yet")
            K11 = ((x1 * x2).sum(dim=-1) + self.offset).pow(self.power)
        else:
            base_inner_prod = torch.matmul(x1, x2.transpose(-2, -1)) + offset
            K11 = base_inner_prod.pow(self.power)

            K12_base = self.power * base_inner_prod.pow(self.power - 1)
            K12 = torch.zeros(*batch_shape, n1, n2 * d)

            ones_ = torch.ones(*batch_shape, d, 1, n2, dtype=K12.dtype, device=K12.device)
            K12_outer_prods = torch.matmul(x1.transpose(-2, -1).unsqueeze(-1), ones_)
            K12 = (K12_base * K12_outer_prods).transpose(-3, -2).contiguous().view(*batch_shape, n1, d * n2)

            ones_ = torch.ones(*batch_shape, d, n1, 1, dtype=K12.dtype, device=K12.device)
            K21_outer_prods = torch.matmul(ones_, x2.transpose(-2, -1).unsqueeze(-2))
            K21 = (K12_base * K21_outer_prods).view(*batch_shape, 2 * n1, n2)

            K22_base = self.power * (self.power - 1) * base_inner_prod.pow(self.power - 2)
            K22 = torch.zeros(*batch_shape, n1 * d, n2 * d)
            all_outers = x1.unsqueeze(-2).unsqueeze(-2).transpose(-2, -1).matmul(x2.unsqueeze(-3).unsqueeze(-2))
            all_outers = all_outers.transpose(-4, -2).transpose(-3, -1)
            K22 = K22_base * all_outers  # d x d x n1 x n2

            # Can't avoid this for loop without unnecessary memory duplication, which is worse.
            for i in range(d):
                K22[i, i] = K22[i, i] + K12_base

            K22 = K22.transpose(-4, -3).transpose(-3, -2).contiguous().view(*batch_shape, n1 * d, n2 * d)

            K = torch.cat([torch.cat([K11, K12], dim=-1), torch.cat([K21, K22], dim=-1)])

            # Apply perfect shuffle
            pi1 = torch.arange(n1 * (d + 1)).view(d + 1, n1).t().contiguous().view((n1 * (d + 1)))
            pi2 = torch.arange(n2 * (d + 1)).view(d + 1, n2).t().contiguous().view((n2 * (d + 1)))
            K = K[..., pi1, :][..., :, pi2]

            return K

    def num_outputs_per_input(self, x1, x2):
        return x1.size(-1) + 1
