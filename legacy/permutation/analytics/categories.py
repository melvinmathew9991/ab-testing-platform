import sys

sys.path.append("..")
sys.path.append("permutation")
from utils.params import (
    UNIT_ID,
    TIME_STAMP_NAME,
    SESSION_ID,
    COUNTRY,
    UserFlowStep,
    PerformanceMetrics,
)

# Configuration typically stored in a system of metrics
CATEGORY_EXAMPLES: dict = {
    # Marketing
    "utm_source": "utm_source",
    # Geography
    # 'country': f'{COUNTRY}',
    "region": f"""CASE
        WHEN {COUNTRY} in ('US', 'CA', 'MX')
          THEN 'North America'
        WHEN {COUNTRY} IN (
            'BE', 'BG', 'CZ', 'DK', 'DE',
            'EE', 'IE', 'EL', 'ES', 'FR',
            'HR', 'IT', 'CY', 'LV', 'LT',
            'LU', 'HU', 'MT', 'NL', 'AT',
            'PL', 'PT', 'RO', 'SI', 'SK',
            'FI', 'SE', )
          THEN 'European Union'
        ELSE 'Rest of the World' END""",
    "international": f"""CASE
        WHEN MIN({COUNTRY}) OVER (
              PARTITION BY {UNIT_ID}) !=
           MAX({COUNTRY}) OVER (
              PARTITION BY {UNIT_ID})
          THEN 'international'
        ELSE 'domestic' END""",
    # Interface
    # 'device_type': 'device_type',
    # 'browser_name': 'browser_name',
    "interface": f"""CASE
        WHEN MIN(device_type) OVER (
            PARTITION BY {UNIT_ID}) !=
          MAX(device_type) OVER (
            PARTITION BY {UNIT_ID})
          THEN 'hybrid'
        ELSE device_type END""",
    # Local Time
    "hour_of_day": f"""
      EXTRACT("hour" FROM
        CONCAT(
          {TIME_STAMP_NAME}, ' ',
          REPLACE(geo_timezone, '-', '_')
        )::TIMESTAMPTZ
      )/4*4""",
    "day_of_week": f"""
      EXTRACT("weekday"
        FROM CONCAT(
          {TIME_STAMP_NAME}, ' ',
          REPLACE(geo_timezone, '-', '_')          
        )::TIMESTAMPTZ
      )""",
    "week_of_year": f"""
      EXTRACT("WEEK"
        FROM {TIME_STAMP_NAME}::TIMESTAMP
      )""",
    #  Activity
    "activity_level": f"""CASE
        WHEN COUNT(1) OVER (
            PARTITION BY {UNIT_ID}
            ) <  3 THEN 'low_activity'
        WHEN COUNT(1) OVER (
            PARTITION BY {UNIT_ID}
            ) < 30 THEN 'some_activity'
        ELSE 'high_activity' END""",
    "deliberate": f"""CASE
        WHEN COUNT(1) OVER (
            PARTITION BY {SESSION_ID}
            ) < 3 THEN 'indifferent'
        WHEN COUNT(1) OVER (
            PARTITION BY {SESSION_ID}
            ) < 6 THEN 'attentive'
        ELSE 'thorough' END""",
    "is_returning": f"""CASE
        WHEN LEAD({SESSION_ID}) OVER (
                PARTITION BY {UNIT_ID}
                ORDER BY {TIME_STAMP_NAME}
            ) IS NULL THEN 'new'                    
        ELSE 'returning' END""",
}

# Those parameters are typically controlled via an drop-
# down or click-to-select interface to be controlled by
# non-technical stakeholders. 
# Those interactions are why Experimentation is so often
# an internal tool with custom configuration and results.

FILTERS_EXAMPLES = {"is_returning": ("new",)}

BREAKDOWN_EXAMPLES = {"utm_source", "region"}

STEP_EXAMPLES = {
    UserFlowStep.CART.value,
    UserFlowStep.CONFIRMATION.value,
}
