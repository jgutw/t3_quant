# t3_quant Math Formulas
Only formulas that can be coded or used as hard constraints.

## 1. Ornstein–Uhlenbeck
dX_t = μ(θ − X_t) dt + σ dB_t

Generator: L = (σ²/2) d²/dx² + μ(θ − x) d/dx

## 2. Optimal entry band with stop-loss (Leung & Li)
L < a* < entry zone < b*
Raising L lowers the optimal take-profit.

## 3. Exponential OU exit threshold
e^b F(b) = (e^b − c_s) F'(b)

Continuation region for entry is disconnected: (0,A) ∪ (B,∞)

## 4. Nested OU for metals EFP
dS_t = σ_S dW^S
dE_t = −k_E (E_t − D_t) dt + σ_E dW^E
dD_t = −k_D (D_t − D̄) dt + σ_D dW^D
F_t = S_t + E_t

## 5. Order Flow Imbalance
e_n = I_{P^B↑} q^B_n − I_{P^B↓} q^B_{n-1} − I_{P^A↓} q^A_n + I_{P^A↑} q^A_{n-1}
OFI_k = Σ e_n
ΔP_k ≈ β · OFI_k / Depth_k

## 6. Deflated Sharpe Ratio (Bailey & LdP)
DSR = (SR̂ − SR̂₀) / √Var(SR̂)
where SR̂₀ is the expected maximum Sharpe under N pure-noise trials.

## 7. Probability of Backtest Overfitting (CSCV)
Split series into S blocks.
For every combination of S/2 blocks as IS and S/2 as OOS:
  rank variants by IS performance
  record whether IS-best underperforms median OOS
PBO = fraction of combinations where this occurs.

## 8. Changepoint severity (Wood et al.)
Standardise returns inside lookback l:
  r̂_t = (r_t − E[r]) / √Var[r]
Compare Matérn-3/2 GP vs changepoint kernel. Severity:
  ν_t = 1 − 1/(1 + exp(−(nlm_CP − nlm_M)))
Location:
  γ_t = (c − (t − l)) / l
Both ∈ (0,1).

## 9. Wasserstein-1 between segment distributions
D_ij = W_1(μ_i, μ_j) = ∫ |F_i − F_j| dx
Affinity for spectral clustering:
  A_ij = exp(−D_ij² / (σ_i σ_j))

## 10. Joint multi-scale regime probability (conceptual)
P_t(i,j,k) = π_t^(1D)(i) × π_t^(4H)(j) × π_t^(1H)(k)
Shannon entropy of the marginal or joint used as uncertainty filter.
