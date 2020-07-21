import math
from typing import Sequence, Optional

import numpy as np
from gym import Env
from gym.envs.registration import EnvSpec
from gym.spaces import Box, Discrete
from yaaf import ndarray_index_from


class MarkovDecisionProcess(Env):

    def __init__(self, name: str,
                 states: Sequence[np.ndarray],
                 actions: Sequence[int],
                 transition_probabilities: np.ndarray,
                 rewards: np.ndarray,
                 discount_factor: float,
                 initial_state_distribution: np.ndarray,
                 min_value_iteration_error: float = 10e-8,
                 state_meanings: Optional[Sequence[str]] = None,
                 action_meanings: Optional[Sequence[str]] = None):

        super(MarkovDecisionProcess, self).__init__()

        # MDP (S, A, P, R, gamma, miu)
        self._states = states
        self._actions = actions
        self.action_space = Discrete(len(actions))
        self._P = transition_probabilities
        self._R = rewards
        self._discount_factor = discount_factor
        self._miu = initial_state_distribution

        # Metadata (OpenAI Gym)
        self.spec = EnvSpec(id=name)
        states_tensor = np.array(states).astype(np.float)
        self.observation_space = Box(
            low=states_tensor.min(),
            high=states_tensor.max(),
            shape=self._states[0].shape,
            dtype=states_tensor.dtype)
        self._num_states = states_tensor.shape[0]
        self._num_actions = len(actions)
        self.reward_range = (rewards.min(), rewards.max())
        self.metadata = {}
        self.state_meanings = state_meanings or []
        self.action_meanings = action_meanings or []

        # Value Iteration
        self._min_value_iteration_error = min_value_iteration_error

        # TODO - Remove this
        self._state = self.reset()

    def reset(self):
        x = np.random.choice(range(self.num_states), p=self._miu)
        initial_state = self._states[x]
        self._state = initial_state
        return initial_state

    def step(self, action):
        next_state, reward = self.transition(self.state, action)
        is_terminal = self.is_terminal(next_state)
        self._state = next_state
        return next_state, reward, is_terminal, {}

    def transition(self, state, action):

        x = self.state_index(state)
        transition_probabilities = self.P[action, x]

        # Next state
        y = np.random.choice(self.num_states, p=transition_probabilities)
        next_state = self.states[y]

        # Reward
        if self.R.shape == (self.num_states, self.num_actions):
            reward = self.R[x, action]
        elif self.R.shape == (self.num_states,):
            reward = self.R[y]
        elif self.R.shape == (self.num_states, self.num_actions, self.num_states):
            reward = self.R[x, action, y]
        else:
            raise ValueError("Invalid reward matrix R.")

        return next_state, reward

    # ############### #
    # Value Iteration #
    # ############### #

    @property
    def policy(self):
        """
        Computes (or returns, if already computed)
        the optimal policy for the MDP using value iteration.
        """
        if not hasattr(self, "_pi"):
            self._pi = np.zeros((self.num_states, self.num_actions))
            for s in range(self.num_states):
                optimal_actions = np.argwhere(self.q_values[s] == self.q_values[s].max()).reshape(-1)
                self._pi[s, optimal_actions] = 1.0 / len(optimal_actions)
        return self._pi

    def evaluate_policy(self, pi):
        """
        Evaluates a given policy pi in the MDP.
        """
        policy_values = np.zeros(self.num_states)
        q = self.q_values
        for s in range(self.num_states):
            policy_values[s] = pi[s].dot(q[s])
        return policy_values

    @property
    def q_values(self) -> np.ndarray:
        if not hasattr(self, "_q_values"): self._q_values, self._V = self._value_iteration()
        return self._q_values

    @property
    def values(self) -> np.ndarray:
        if not hasattr(self, "_values"): self._Qstar, self._values = self._value_iteration()
        return self._values

    def _value_iteration(self):

        """
        Solves the MDP using value iteration
        Returns the Optimal Q function Q*
        """

        A = self.num_actions
        X = self.num_states
        P = self.P

        if self.R.shape == (X, A):
            R = self.R
        elif self.R.shape == (X,):
            # FIXME - Find clever way
            R = np.zeros((X, A))
            for state in self.states:
                s = self.state_index(state)
                R[s, :] = self.R[s]
        elif self.R.shape == (X, A, X):
            # TODO
            raise NotImplementedError()
        else:
            raise ValueError("Invalid reward matrix.")

        V = np.zeros(X)
        Q = np.zeros((X, A))

        error = math.inf
        while error > self._min_value_iteration_error:
            for a in range(A):
                Q[:, a] = R[:, a] + self._discount_factor * P[a].dot(V)
            Qa = tuple([Q[:, a] for a in range(A)])
            V_new = np.max(Qa, axis=0)
            error = np.linalg.norm(V_new - V)
            V = V_new

        return Q, V

    # ########## #
    # Properties #
    # ########## #

    @property
    def state(self):
        return self._state

    @property
    def states(self):
        return self._states

    @property
    def num_states(self):
        return self._num_states

    @property
    def actions(self):
        return self._actions

    @property
    def num_actions(self):
        return self._num_actions

    @property
    def transition_probabilities(self):
        """Returns the Transition Probabilities P (array w/ shape X, X)"""
        return self._P

    @property
    def P(self):
        """Alias for self.transition_probabilities"""
        return self.transition_probabilities

    @property
    def rewards(self):
        """Returns the Rewards R (array w/ shape X, A)"""
        return self._R

    @property
    def R(self):
        """Alias for self.rewards"""
        return self.rewards

    @property
    def discount_factor(self):
        return self._discount_factor

    @property
    def gamma(self):
        """Alias for self.discount_factor"""
        return self._discount_factor

    @property
    def initial_state_distribution(self):
        return self._miu

    @property
    def miu(self):
        return self._miu

    # ######### #
    # Auxiliary #
    # ######### #

    def state_index(self, state=None):
        """
            Returns the index of a given state in the state space.
            If the state is unspecified (None), returns the index of the current state st.
        """
        return self.state_index(self.state) if state is None else self.state_index_from(self.states, state)

    @staticmethod
    def state_index_from(states, state):
        """Returns the index of a state (array) in a list of states"""
        return ndarray_index_from(states, state)

    def is_terminal(self, state):
        return False