"""
The `train` subcommand can be used to train a model.
It requires a configuration file and a directory in
which to write the results.
"""

import argparse
import json
import logging
import os
from functools import partial

import optuna
from allennlp.commands.subcommand import Subcommand
from optuna import Trial
from optuna.integration import AllenNLPExecutor
from overrides import overrides

logger = logging.getLogger(__name__)


def optimize_hyperparameters(args: argparse.Namespace) -> None:
    config_file = args.param_path
    hparam_path = args.hparam_path
    optuna_param_path = args.optuna_param_path
    serialization_dir = args.serialization_dir

    load_if_exists = args.skip_if_exists
    direction = args.direction
    n_trials = args.n_trials
    timeout = args.timeout
    study_name = args.study_name
    storage = args.storage
    metrics = args.metrics

    os.makedirs(serialization_dir, exist_ok=True)

    def _objective(
        trial: Trial,
        hparam_path: str,
    ) -> float:

        for hparam in json.load(open(hparam_path)):
            attr_type = hparam["type"]
            suggest = getattr(trial, "suggest_{}".format(attr_type))
            suggest(**hparam["keyword"])

        optuna_serialization_dir = os.path.join(serialization_dir, "trial_{}".format(trial.number))
        executor = AllenNLPExecutor(trial, config_file, optuna_serialization_dir, metrics=metrics)
        return executor.run()

    if optuna_param_path is not None and os.path.isfile(optuna_param_path):
        optuna_config = json.load(open(optuna_param_path))
    else:
        optuna_config = {}

    if "pruner" in optuna_config:
        pruner_class = getattr(optuna.pruners, optuna_config["pruner"]["type"])
        pruner = pruner_class(**optuna_config["pruner"]["keyword"])
    else:
        pruner = None

    if "sampler" in optuna_config:
        sampler_class = getattr(optuna.samplers, optuna_config["sampler"]["type"])
        sampler = sampler_class(optuna_config["sampler"]["keyword"])
    else:
        sampler = None

    study = optuna.create_study(
        study_name=study_name,
        direction=direction,
        storage=storage,
        pruner=pruner,
        sampler=sampler,
        load_if_exists=load_if_exists,
    )

    objective = partial(
        _objective,
        hparam_path=hparam_path,
    )
    study.optimize(objective, n_trials=n_trials, timeout=timeout)


def export_hyperparameters(args: argparse.Namespace) -> None:
    storage = args.storage
    study_name = args.study_name
    study = optuna.load_study(study_name=study_name, storage=storage)
    print(" ".join("{}={}".format(k, v) for k, v in study.best_params.items()))


@Subcommand.register("allenopt")
class AllenOpt(Subcommand):
    @overrides
    def add_subparser(self, parser: argparse._SubParsersAction) -> argparse.ArgumentParser:
        description = """Train the specified model on the specified dataset."""
        subparser = parser.add_parser(self.name, description=description, help="Train a model.")

        subparser.add_argument(
            "param_path",
            type=str,
            help="path to parameter file describing the model to be trained",
        )

        subparser.add_argument(
            "hparam_path",
            type=str,
            help="path to hyperparameter file",
            default="hyper_params.json",
        )

        subparser.add_argument(
            "--optuna-param-path",
            type=str,
            help="path to Optuna config",
        )

        subparser.add_argument(
            "--serialization-dir",
            required=True,
            type=str,
            help="directory in which to save the model and its logs",
        )

        # ---- Optuna -----

        subparser.add_argument(
            "--skip-if-exists",
            default=False,
            action="store_true",
            help="If specified, the creation of the study is skipped "
            "without any error when the study name is duplicated.",
        )

        subparser.add_argument(
            "--direction",
            type=str,
            choices=("minimize", "maximize"),
            default="minimize",
            help="Set direction of optimization to a new study. Set 'minimize' "
            "for minimization and 'maximize' for maximization.",
        )

        subparser.add_argument(
            "--n-trials",
            type=int,
            help="The number of trials. If this argument is not given, as many " "trials run as possible.",
            default=50,
        )

        subparser.add_argument(
            "--timeout",
            type=float,
            help="Stop study after the given number of second(s). If this argument"
            " is not given, as many trials run as possible.",
        )

        subparser.add_argument(
            "--study-name", default=None, help="The name of the study to start optimization on."
        )

        subparser.add_argument(
            "--storage",
            type=str,
            help=(
                "The path to storage. AllenOpt supports a valid URL" "for sqlite3, mysql, postgresql, or redis."
            ),
            default="sqlite:///allenopt.db",
        )

        subparser.add_argument(
            "--metrics",
            type=str,
            help="The metrics you want to optimize.",
            default="best_validation_loss",
        )

        subparser.set_defaults(func=optimize_hyperparameters)
        return subparser


@Subcommand.register("best-params")
class AllenOptExport(Subcommand):
    @overrides
    def add_subparser(self, parser: argparse._SubParsersAction) -> argparse.ArgumentParser:
        description = """Export best hyperparameters in the trials."""
        subparser = parser.add_parser(self.name, description=description, help="Export best hyperparameters.")

        subparser.add_argument(
            "--study-name", default=None, help="The name of the study to start optimization on."
        )

        subparser.add_argument(
            "--storage",
            type=str,
            help=(
                "The path to storage. AllenOpt supports a valid URL" "for sqlite3, mysql, postgresql, or redis."
            ),
            default="sqlite:///allenopt.db",
        )

        subparser.set_defaults(func=export_hyperparameters)
        return subparser
