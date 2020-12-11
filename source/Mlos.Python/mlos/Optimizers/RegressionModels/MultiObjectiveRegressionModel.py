#
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
#
from abc import ABC, abstractmethod

import pandas as pd

from mlos.Spaces import Hypergrid, Point
from mlos.Optimizers.RegressionModels.MultiObjectivePrediction import MultiObjectivePrediction


class MultiObjectiveRegressionModel(ABC):
    """An interface for all multi-objective regression models to implement."""


    @abstractmethod
    def __init__(
        self,
        model_type: type,
        model_config: Point,
        input_space: Hypergrid,
        output_space: Hypergrid
    ):
        self.model_type = model_type
        self.model_config = model_config
        self.input_space = input_space
        self.output_space = output_space

    @abstractmethod
    def fit(self, features_df: pd.DataFrame, targets_df: pd.DataFrame, iteration_number: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def predict(
        self,
        features_df: pd.DataFrame,
        targets_df: pd.DataFrame,
        include_only_valid_rows: bool=True
    ) -> MultiObjectivePrediction:
        raise NotImplementedError