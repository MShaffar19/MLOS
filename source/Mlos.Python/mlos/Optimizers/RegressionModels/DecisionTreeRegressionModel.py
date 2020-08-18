#
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
#
from enum import Enum
import numpy as np
from sklearn.tree import DecisionTreeRegressor

from mlos.Logger import create_logger
from mlos.Optimizers.RegressionModels.Prediction import Prediction
from mlos.Optimizers.RegressionModels.RegressionModel import RegressionModel, RegressionModelConfig
from mlos.Spaces import Hypergrid, SimpleHypergrid, ContinuousDimension, DiscreteDimension, CategoricalDimension, Point
from mlos.Tracer import trace


class DecisionTreeRegressionModelConfig(RegressionModelConfig):
    """ A configuration object for a decision tree regression model.

    This class is responsible for validating that its objects are valid configurations.
    DecisionTreeRegressionModel will take an object of this class to actually create
    the model.
    """

    class Criterion(Enum):
        """ The function to measure the quality of a split.

        Supported criteria are 'mse' for the mean squared error, which is equal to variance reduction as feature
        selection criterion and minimizes the L2 loss using the mean of each terminal node, 'friedman_mse',
        which uses mean squared error with Friedman’s improvement score for potential splits, and 'mae' for the
        mean absolute error, which minimizes the L1 loss using the median of each terminal node.

        Copied from scikit-learn docs.
        """
        MSE = 'mse'
        FRIEDMAN_MSE = 'friedman_mse'
        MAE = 'mae'

    class Splitter(Enum):
        """ The strategy used to choose the split at each node.

        Supported strategies are “best” to choose the best split and “random” to choose the best random split.
        """
        BEST = "best"
        RANDOM = "random"

    class MaxFeaturesFunc(Enum):
        AUTO = "auto"
        SQRT = "sqrt"
        LOG2 = "log2"

    CONFIG_SPACE = SimpleHypergrid(
        name="decision_tree_regression_model_config",
        dimensions=[
            CategoricalDimension(name="criterion", values=[criterion.value for criterion in Criterion]),
            CategoricalDimension(name="splitter", values=[splitter.value for splitter in Splitter]),
            DiscreteDimension(name="max_depth", min=0, max=2**10),
            DiscreteDimension(name="min_samples_split", min=2, max=2**10),
            DiscreteDimension(name="min_samples_leaf", min=3, max=2**10),
            ContinuousDimension(name="min_weight_fraction_leaf", min=0.0, max=0.5),
            CategoricalDimension(name="max_features", values=[function.value for function in MaxFeaturesFunc]),
            DiscreteDimension(name="max_leaf_nodes", min=0, max=2**10),
            ContinuousDimension(name="min_impurity_decrease", min=0.0, max=2**10),
            ContinuousDimension(name="ccp_alpha", min=0.0, max=2**10),
            DiscreteDimension(name="min_samples_to_fit", min=1, max=2 ** 32),
            DiscreteDimension(name="n_new_samples_before_refit", min=1, max=2**32)
        ]
    )

    DEFAULT = Point(
        criterion=Criterion.MSE.value,
        splitter=Splitter.RANDOM.value,
        max_depth=0,
        min_samples_split=2,
        min_samples_leaf=3,
        min_weight_fraction_leaf=0.0,
        max_features=MaxFeaturesFunc.AUTO.value,
        max_leaf_nodes=0,
        min_impurity_decrease=0.0,
        ccp_alpha=0.0,
        min_samples_to_fit=50,
        n_new_samples_before_refit=10
    )

    @classmethod
    def contains(cls, config):
        return Point(
            criterion=config.criterion,
            splitter=config.splitter,
            max_depth=config.max_depth,
            min_samples_split=config.min_samples_split,
            min_samples_leaf=config.min_samples_leaf,
            min_weight_fraction_leaf=config.min_weight_fraction_leaf,
            max_features=config.max_features,
            max_leaf_nodes=config.max_leaf_nodes,
            min_impurity_decrease=config.min_impurity_decrease,
            ccp_alpha=config.ccp_alpha,
            min_samples_to_fit=config.min_samples_to_fit,
            n_new_samples_before_refit=config.n_new_samples_before_refit
        ) in cls.CONFIG_SPACE

    @classmethod
    def create_from_config_point(cls, config_point):
        assert cls.contains(config_point)
        config_key_value_pairs = {param_name: value for param_name, value in config_point}
        return cls(**config_key_value_pairs)

    def __init__(
            self,
            criterion=Criterion.MSE.value,
            splitter=Splitter.RANDOM.value,
            max_depth=0,
            min_samples_split=2,  # TODO: decouple the int/float interpretation
            min_samples_leaf=3,  # Default to 3 so that there is variance. # TODO: decouple the int/float interpretation
            min_weight_fraction_leaf=0.0,
            max_features=MaxFeaturesFunc.AUTO.value,   # TODO: decouple the int/float/str interpretation
            random_state=None,
            max_leaf_nodes=0,
            min_impurity_decrease=0.0,
            ccp_alpha=0.0,
            min_samples_to_fit=DEFAULT.min_samples_to_fit,
            n_new_samples_before_refit=DEFAULT.n_new_samples_before_refit
    ):
        """
        :param criterion: The function to measure the quality of a split.
        :param splitter: The strategy used to choose the split at each node.
        :param max_depth: The maximum depth of the tree. If None, then nodes are expanded until all leaves are pure or until all leaves contain less than
                min_samples_split samples.
        :param min_samples_split: The minimum number of samples required to split an internal node.
        :param min_samples_leaf: The minimum number of samples required to be at a leaf node.
        :param min_weight_fraction_leaf: The minimum weighted fraction of the sum total of weights (of all the input samples) required to be at a leaf node.
                Samples have equal weight when sample_weight is not provided.
        :param max_features: The number of features to consider when looking for the best split.
        :param random_state: If int, random_state is the seed used by the random number generator; If RandomState instance, random_state is the random number
                generator; If None, the random number generator is the RandomState instance used by np.random.
        :param max_leaf_nodes: Grow a tree with max_leaf_nodes in best-first fashion. Best nodes are defined as relative reduction in impurity. If None then
                unlimited number of leaf nodes.
        :param min_impurity_decrease: A node will be split if this split induces a decrease of the impurity greater than or equal to this value.
        :param ccp_alpha: complexity parameter used for Minimal Cost-Complexity Pruning. The subtree with the largest cost complexity that is smaller than
                ccp_alpha will be chosen. By default, no pruning is performed. See Minimal Cost-Complexity Pruning for details.
        :param min_samples_to_fit: minimum number of samples before it makes sense to try to fit this tree
        :param n_new_samples_before_refit: It makes little sense to refit every model for every sample. This parameter controls
                how frequently we refit the decision tree.
        """
        self.criterion = criterion
        self.splitter = splitter
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.min_samples_leaf = min_samples_leaf
        self.min_weight_fraction_leaf = min_weight_fraction_leaf
        self.max_features = max_features
        self.random_state = random_state
        self.max_leaf_nodes = max_leaf_nodes
        self.min_impurity_decrease = min_impurity_decrease
        self.ccp_alpha = ccp_alpha
        self.min_samples_to_fit = min_samples_to_fit
        self.n_new_samples_before_refit = n_new_samples_before_refit

    @property
    def max_depth_value(self):
        if self.max_depth == 0:
            return None
        return self.max_depth

    @property
    def max_leaf_nodes_value(self):
        if self.max_leaf_nodes == 0 or self.max_leaf_nodes == 1:
            return None
        return self.max_leaf_nodes

class DecisionTreeRegressionModel(RegressionModel):
    """
    Possible extensions:
    * have a tree fit a linear model at each leaf.
    """

    def __init__(
            self,
            model_config: DecisionTreeRegressionModelConfig,
            input_space: Hypergrid,
            output_space: Hypergrid,
            logger=None
    ):
        if logger is None:
            logger = create_logger("DecisionTreeRegressionModel")
        self.logger = logger

        assert DecisionTreeRegressionModelConfig.contains(model_config)
        super(DecisionTreeRegressionModel, self).__init__(model_type=type(self), model_config=model_config)

        # TODO: move to RegressionModel?
        self.input_space = input_space
        self.output_space = output_space

        self.input_dimension_names = [dimension.name for dimension in self.input_space.dimensions]
        self.target_dimension_names = [dimension.name for dimension in self.output_space.dimensions]
        self.logger.debug(f"Input dimensions: {str(self.input_dimension_names)}; Target dimensions: {str(self.target_dimension_names)}.")

        assert len(self.target_dimension_names) == 1, "For now (and perhaps forever) we only support single target per tree."

        self._regressor = DecisionTreeRegressor(
            criterion=self.model_config.criterion,
            splitter=self.model_config.splitter,
            max_depth=self.model_config.max_depth_value,
            min_samples_split=self.model_config.min_samples_split,
            min_samples_leaf=self.model_config.min_samples_leaf,
            min_weight_fraction_leaf=self.model_config.min_weight_fraction_leaf,
            max_features=self.model_config.max_features,
            random_state=self.model_config.random_state,
            max_leaf_nodes=self.model_config.max_leaf_nodes_value,
            min_impurity_decrease=self.model_config.min_impurity_decrease,
            ccp_alpha=self.model_config.ccp_alpha
        )

        # These are used to compute the variance in predictions
        self._observations_per_leaf = dict()
        self._predictions_per_leaf = dict()

        self.fitted = False
        self.num_observations_used_to_fit = 0

    def should_fit(self, num_samples):
        """ Returns true if the model should be fitted.

        This model should be fitted under the following conditions:
        1) It has not been fitted yet and num_samples is larger than min_samples_to_fit
        2) The model has been fitted and the number of new samples is larger than n_new_samples_before_refit

        :param num_samples:
        :return:
        """
        if not self.fitted:
            return num_samples > self.model_config.min_samples_to_fit
        num_new_samples = num_samples - self.num_observations_used_to_fit
        return num_new_samples > self.model_config.n_new_samples_before_refit

    @trace()
    def fit(self, feature_values_pandas_frame, target_values_pandas_frame):
        self.logger.debug(f"Fitting a {self.__class__.__name__} with {len(feature_values_pandas_frame.index)} observations.")

        # Let's get the numpy arrays out of the panda frames
        #
        feature_values = feature_values_pandas_frame[self.input_dimension_names].to_numpy()
        target_values = target_values_pandas_frame[self.target_dimension_names].to_numpy()

        # Clean up state before fitting again
        self._observations_per_leaf = dict()
        self._predictions_per_leaf = dict()

        self._regressor.fit(feature_values, target_values)

        # Now that we have fit the model we can augment our tree by computing the variance
        # TODO: this code can be easily optimized, but premature optimization is the root of all evil.
        node_indices = self._regressor.apply(feature_values)
        self.logger.debug(f"The resulting three has {len(node_indices)} leaf nodes.")

        for node_index, sample_target_value in zip(node_indices, target_values):
            observations_at_leaf = self._observations_per_leaf.get(node_index, [])
            observations_at_leaf.append(sample_target_value)
            self._observations_per_leaf[node_index] = observations_at_leaf

        # Now let's compute all predictions
        for node_index in self._observations_per_leaf:
            # First convert the observations to a numpy array.
            observations_at_leaf = np.array(self._observations_per_leaf[node_index])
            self._observations_per_leaf[node_index] = observations_at_leaf

            leaf_mean = np.mean(observations_at_leaf)
            leaf_variance = np.var(observations_at_leaf, ddof=1) # ddof = delta degrees of freedom. We want sample variance.

            # TODO: note that if we change the tree to fit a linear regression at each leaf, these predictions would have
            # to be computed in the .predict() function, though the slope and y-intersect could be computed here.
            prediction = Prediction(target_name=self.target_dimension_names[0], mean=leaf_mean, variance=leaf_variance, count=len(observations_at_leaf))
            self._predictions_per_leaf[node_index] = prediction

        self.fitted = True

    @trace()
    def predict(self, feature_values_pandas_frame):
        self.logger.debug(f"Creating predictions for {len(feature_values_pandas_frame.index)} samples.")
        predictions = []

        if not self.fitted:
            # We haven't been fitted so we return a lot of empty predictions
            self.logger.debug("Decision tree has not been fitted. Returning None predictions.")
            for row in range(len(feature_values_pandas_frame.index)):
                predictions.append(Prediction(target_name=self.target_dimension_names[0], valid=False))
        else:
            # Instead of calling self._regressor.predict() we consult the _observations_per_leaf()
            # to get the variance as well

            # Let's get the numpy arrays out of the panda frames
            # TODO: move to common function
            #
            input_dimension_names = [dimension.name for dimension in self.input_space.dimensions]
            feature_values = feature_values_pandas_frame[input_dimension_names].to_numpy()

            # TODO: this is wasteful and slow. we should make sure that only rows with adequate data are passed into this function
            predictions = []
            for row in feature_values:
                # TODO: row_point = Point(**{name: value for name, value in zip(self.input_dimension_names, row)})
                if np.isnan(row).any(): # TODO: or row_point not in self.input_space:
                    # This row has missing data - no prediction possible
                    predictions.append(Prediction(target_name=self.target_dimension_names[0], valid=False))
                else:
                    leaf_node_index = self._regressor.apply([row])[0]
                    prediction = self._predictions_per_leaf[leaf_node_index]
                    predictions.append(prediction)
        return predictions