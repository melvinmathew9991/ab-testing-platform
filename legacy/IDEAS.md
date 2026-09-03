
# Improvements ideas and new feature 

## Interface
* [ ] Add an FastAPI interface to integrate with an internal admin.
* [ ] Server hosting 

## Performance
* [ ] If conversion_rate has more than 100,000 users,
      optimize for scale by aggregating into 10,000 cells first,
      then reassiging every cell to a random variant        

## Expand Experiment 
* [ ] Multiple variants
  * Control vs. Each treatement or All vs. All?
  * Implement Dunnett's test?

## Metrics 
* [ ] Introduce support for ratio of more than one event
  *  Product consideration
* [ ] Support metric grammar (dbt) for non-ratio metrics

## Statistics:
* [ ] Control Family-wise error rates (FWER)
  * [ ] Multi-comparison corrections for breakdowns
  * [ ] Multi-variate tests ('A/B/C/D tests')
  * [ ] Sequential tests
  * [ ] Dunnett's test for many metrics?
