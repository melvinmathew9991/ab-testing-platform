import sys

sys.path.append("..")
sys.path.append("permutation")
from utils.params import (
    UNIT_ID,
    SESSION_ID,
    STEP_NAME,
    STEPS_URL_LABEL,
    TIME_STAMP_NAME,
)

METRICS_DEFINITIONS = {
    "metrics": """
        , """.join(
        [
            f"({STEP_NAME} = {v}) AS reach_{k}"
            for k, v in STEPS_URL_LABEL.items()
        ]
        + [
            f"""
            DATEDIFF(
              'seconds',
              {TIME_STAMP_NAME}::TIMESTAMP,
              LEAD({TIME_STAMP_NAME}) OVER (
                PARTITION BY {SESSION_ID}
                ORDER BY {TIME_STAMP_NAME}
              )::TIMESTAMP                
            ) AS delay_{k}"""
            for k, v in STEPS_URL_LABEL.items()
        ]
        + [
            f"""CASE WHEN 
                LEAD({UNIT_ID}) OVER (
                    PARTITION BY {SESSION_ID}
                    ORDER BY {TIME_STAMP_NAME}
                ) IS NULL THEN 1 ELSE 0 END
            AS abandonment_{k}"""
            for k, v in STEPS_URL_LABEL.items()
        ]
    ),
    "score": """
        , """.join( 
        [   f"BOOL_OR(reach_{k}) AS reach_{k}"
            for k, v in STEPS_URL_LABEL.items()
        ]+[
            f"""AVG(delay_{k}) AS delay_{k}"""
            for k, v in STEPS_URL_LABEL.items()
        ]+[
            f"""AVG(abandonment_{k}) AS abandonment_{k}"""
            for k, v in STEPS_URL_LABEL.items()
        ]
    ),
    "aggregate": """
        , """.join(
        [
            f"""COUNT(reach_{k} = 1) * 1.0 /
            COUNT({UNIT_ID}) AS reach_{k}"""
            for k in STEPS_URL_LABEL.keys()
        ]
        + [
            f"""AVG(delay_{k}) AS delay_{k}"""
            for k, v in STEPS_URL_LABEL.items()
        ]
        + [
            f"""AVG(abandonment_{k}) AS abandonment_{k}"""
            for k, v in STEPS_URL_LABEL.items()
        ]
    ),
}
