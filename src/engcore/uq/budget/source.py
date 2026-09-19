from enum import Enum

class UncertaintySource(str,Enum):
    MEASUREMENT="measurement"
    PARAMETER="parameter"
    NUMERICAL="numerical"
    MODEL_FORM="model_form"
    BOUNDARY_CONDITION="boundary_condition"
    INITIAL_CONDITION="initial_condition"
    CALIBRATION="calibration"
    DATASET="dataset"
    EXPERIMENTAL_VARIABILITY="experimental_variability"
