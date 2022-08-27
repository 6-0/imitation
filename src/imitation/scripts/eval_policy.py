"""Evaluate policies: render policy interactively, save videos, log episode return."""

import logging
import pathlib
import re
import time
from typing import Any, Mapping, Optional

import gym
from sacred.observers import FileStorageObserver
from stable_baselines3.common.vec_env import VecEnvWrapper

from imitation.data import rollout, types
from imitation.policies import serialize
from imitation.rewards import reward_wrapper
from imitation.rewards.serialize import load_reward
from imitation.scripts.common import common
from imitation.scripts.config.eval_policy import eval_policy_ex
from imitation.util import video_wrapper


class InteractiveRender(VecEnvWrapper):
    """Render the wrapped environment(s) on screen."""

    def __init__(self, venv, fps):
        """Builds renderer for `venv` running at `fps` frames per second."""
        super().__init__(venv)
        self.render_fps = fps

    def reset(self):
        ob = self.venv.reset()
        self.venv.render()
        return ob

    def step_wait(self):
        ob = self.venv.step_wait()
        if self.render_fps > 0:
            time.sleep(1 / self.render_fps)
        self.venv.render()
        return ob


def video_wrapper_factory(log_dir: pathlib.Path, **kwargs):
    """Returns a function that wraps the environment in a video recorder."""

    def f(env: gym.Env, i: int) -> video_wrapper.VideoWrapper:
        """Wraps `env` in a recorder saving videos to `{log_dir}/videos/{i}`."""
        directory = log_dir / "videos" / str(i)
        return video_wrapper.VideoWrapper(env, directory=directory, **kwargs)

    return f


@eval_policy_ex.main
def eval_policy(
    _run,
    _seed: int,
    eval_n_timesteps: Optional[int],
    eval_n_episodes: Optional[int],
    render: bool,
    render_fps: int,
    videos: bool,
    video_kwargs: Mapping[str, Any],
    policy_type: Optional[str],
    policy_path: Optional[str],
    reward_type: Optional[str] = None,
    reward_path: Optional[str] = None,
    rollout_save_path: Optional[str] = None,
):
    """Rolls a policy out in an environment, collecting statistics.

    Args:
        _seed: generated by Sacred.
        eval_n_timesteps: Minimum number of timesteps to evaluate for. Set exactly
            one of `eval_n_episodes` and `eval_n_timesteps`.
        eval_n_episodes: Minimum number of episodes to evaluate for. Set exactly
            one of `eval_n_episodes` and `eval_n_timesteps`.
        render: If True, renders interactively to the screen.
        render_fps: The target number of frames per second to render on screen.
        videos: If True, saves videos to `log_dir`.
        video_kwargs: Keyword arguments passed through to `video_wrapper.VideoWrapper`.
        policy_type: A unique identifier for the saved policy,
            defined in POLICY_CLASSES. If None, then uses a random policy.
        policy_path: A path to the serialized policy.
        reward_type: If specified, overrides the environment reward with
            a reward of this.
        reward_path: If reward_type is specified, the path to a serialized reward
            of `reward_type` to override the environment reward with.
        rollout_save_path: where to save rollouts used for computing stats to disk;
            if None, then do not save.

    Returns:
        Return value of `imitation.util.rollout.rollout_stats()`.
    """
    log_dir = common.make_log_dir()
    sample_until = rollout.make_sample_until(eval_n_timesteps, eval_n_episodes)
    post_wrappers = [video_wrapper_factory(log_dir, **video_kwargs)] if videos else None
    with common.make_venv(post_wrappers=post_wrappers) as venv:
        if render:
            venv = InteractiveRender(venv, render_fps)

        if reward_type is not None:
            reward_fn = load_reward(reward_type, reward_path, venv)
            venv = reward_wrapper.RewardVecEnvWrapper(venv, reward_fn)
            logging.info(f"Wrapped env in reward {reward_type} from {reward_path}.")

        policy = None
        if policy_type is not None:
            policy = serialize.load_policy(policy_type, policy_path, venv)
        trajs = rollout.generate_trajectories(policy, venv, sample_until)

    if rollout_save_path:
        types.save(rollout_save_path.replace("{log_dir}", log_dir), trajs)

    return rollout.rollout_stats(trajs)


def main_console():
    observer_path = pathlib.Path.cwd() / "output" / "sacred" / "eval_policy"
    observer = FileStorageObserver(observer_path)
    eval_policy_ex.observers.append(observer)
    eval_policy_ex.run_commandline()


if __name__ == "__main__":  # pragma: no cover
    main_console()
