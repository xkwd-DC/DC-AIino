"""A small LSTM implemented with NumPy only (forward + BPTT + Adam).

Written because the deep-learning framework could not be installed in this
environment. The gradients are checked against finite differences before use.
"""

from __future__ import annotations

import numpy as np


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


class NumpyLSTM:
    """Single-layer LSTM with a linear output head."""

    def __init__(self, n_features: int, hidden: int = 8, seed: int = 42) -> None:
        rng = np.random.default_rng(seed)
        self.h = hidden
        scale = 0.1
        self.Wx = rng.normal(0, scale, (n_features, 4 * hidden))
        self.Wh = rng.normal(0, scale, (hidden, 4 * hidden))
        self.b = np.zeros(4 * hidden)
        self.Wo = rng.normal(0, scale, (hidden, 1))
        self.bo = np.zeros(1)

    def parameters(self) -> list[np.ndarray]:
        return [self.Wx, self.Wh, self.b, self.Wo, self.bo]

    # ---------------- forward ----------------
    def forward(self, x: np.ndarray, cache: bool = False):
        n, steps, _ = x.shape
        h = np.zeros((n, self.h))
        c = np.zeros((n, self.h))
        store = []
        for t in range(steps):
            x_t = x[:, t, :]
            z = x_t @ self.Wx + h @ self.Wh + self.b
            i = sigmoid(z[:, : self.h])
            f = sigmoid(z[:, self.h: 2 * self.h])
            o = sigmoid(z[:, 2 * self.h: 3 * self.h])
            g = np.tanh(z[:, 3 * self.h:])
            c_prev, h_prev = c, h
            c = f * c + i * g
            h = o * np.tanh(c)
            if cache:
                store.append((x_t, h_prev, c_prev, i, f, o, g, c))
        y = h @ self.Wo + self.bo
        return (y, store, h) if cache else y

    # ---------------- backward ----------------
    def backward(self, store, h_last: np.ndarray, dy: np.ndarray):
        grads = [np.zeros_like(p) for p in self.parameters()]
        dWx, dWh, db, dWo, dbo = grads
        dWo += h_last.T @ dy
        dbo += dy.sum(axis=0)
        dh = dy @ self.Wo.T
        dc = np.zeros_like(h_last)
        for x_t, h_prev, c_prev, i, f, o, g, c in reversed(store):
            tanh_c = np.tanh(c)
            do = dh * tanh_c
            dc = dc + dh * o * (1 - tanh_c ** 2)
            dz_o = do * o * (1 - o)
            dz_i = (dc * g) * i * (1 - i)
            dz_f = (dc * c_prev) * f * (1 - f)
            dz_g = (dc * i) * (1 - g ** 2)
            dz = np.concatenate([dz_i, dz_f, dz_o, dz_g], axis=1)
            dWx += x_t.T @ dz
            dWh += h_prev.T @ dz
            db += dz.sum(axis=0)
            dh = dz @ self.Wh.T
            dc = dc * f
        return grads


def loss_and_grad(model: NumpyLSTM, x: np.ndarray, y: np.ndarray):
    pred, store, h_last = model.forward(x, cache=True)
    diff = pred - y
    loss = float(np.mean(diff ** 2))
    dy = 2 * diff / len(x)
    return loss, model.backward(store, h_last, dy)


def gradient_check(seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    model = NumpyLSTM(n_features=4, hidden=3, seed=1)
    x = rng.normal(size=(5, 3, 4))
    y = rng.normal(size=(5, 1))
    _, grads = loss_and_grad(model, x, y)
    worst = 0.0
    eps = 1e-5
    for p, g in zip(model.parameters(), grads):
        flat = p.reshape(-1)
        gflat = g.reshape(-1)
        for index in rng.choice(flat.size, size=min(6, flat.size), replace=False):
            original = flat[index]
            flat[index] = original + eps
            plus, _ = loss_and_grad(model, x, y)
            flat[index] = original - eps
            minus, _ = loss_and_grad(model, x, y)
            flat[index] = original
            numeric = (plus - minus) / (2 * eps)
            denom = max(1e-8, abs(numeric) + abs(gflat[index]))
            worst = max(worst, abs(numeric - gflat[index]) / denom)
    return worst


def train(model: NumpyLSTM, x: np.ndarray, y: np.ndarray, epochs: int = 80,
          lr: float = 0.02) -> list[float]:
    params = model.parameters()
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]
    b1, b2, eps = 0.9, 0.999, 1e-8
    history = []
    for step in range(1, epochs + 1):
        loss, grads = loss_and_grad(model, x, y)
        history.append(loss)
        for idx, (p, g) in enumerate(zip(params, grads)):
            m[idx] = b1 * m[idx] + (1 - b1) * g
            v[idx] = b2 * v[idx] + (1 - b2) * g * g
            m_hat = m[idx] / (1 - b1 ** step)
            v_hat = v[idx] / (1 - b2 ** step)
            p -= lr * m_hat / (np.sqrt(v_hat) + eps)
    return history
