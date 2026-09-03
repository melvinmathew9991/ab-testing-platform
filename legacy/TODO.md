# Remains to do

- Unit testing
- Integration testing
- Enums and shared constants
- decorators
  - dataclass
  - property
  - check_output


Implementation decisions and code practices common in high-growth and larger companies are covered in the [following videos](…).

* [ ] Add start date/end date for each experiment
* [ ] Add experiment name
* [ ] Add JSon in assignemnt with experiment name
* [ ] Add time between transations as a metric
  * [ ] Quantile
* [ ] Add number of returns


* [x] Introduction - 4 min
  * Experimentation vs. A/B tests 
    * Humility approach: 80% failure
    * vs. Feature flag vs. Causal inference
  * Why run A/B tests on every change
    * Testing retraction
  * Expectation from this course
  * Why show implementat: Buy over build, but understand
  * Structure of this courses, possible extensions
  * Structure of the code (with graphs)
  
* [x] Notebook -- 10 min
  * [ ] for basic ABTesting
    * [ ] Welsch’s t-test stats
    * [ ] Sharing Results, manual re-running
    * [ ] Results rarely significant: sequential
  * [ ] Anticipate: power analysis
    * [ ] Ramdomize per user, not event
    * [ ] 10_000 is better than 100
  

* [x] Data generation & extraction if you have event logs - 7 min
  * External library, realistic logs
  * Define a transition graph, schedule
  * Code
    * Define as local YML
    * Deploy two instances to reflex an improvement
    * Merge by appending data-frames
    * Storing into db — DuckDB for example 
    * Pickling vs. Appache Arrow
  
  * Data extraction if you have event logs - 4 min
    * Unique ID, Events and conversion
    * Possible alternative metrics
  * Code would be specific to your data source
    * Key point: when to trigger it
  
* [x] First report and attribution - 6 min
  * [Basic SQL](https://www.youtube.com/playlist?list=PL21kTsq1t_-kA8aET667XjUrx8xjfXfwD)
  * Data patterns to reprent overall information
  * SQL code to match reporting
    * Inheritance and Strategy pattern
  * Possibly tricky: Attribution if separate event
  * Code
    * SQL patterns
    * Storing results as passed data frame and in db    
  * Code stop point on data frame

* [x] A/B test - 8 min
  * First, Notebook
    * Quick, five lines
    * but point is reproduceable
  * Stop point on dataframe
  * Code 
    * Extracting the data from report
    * Unit tests
    * Metrics listed as Enum
    * Multi-index results, Categories
    * Computing statistics
    * Unit test to check results:
      * Define: positive, negative, failure
    * Possible complication: double columns index
  * Relevance of efficiency
    * [Profile with other processes](https://towardsdatascience.com/effectively-use-timeit-lprun-and-mprun-to-write-efficient-python-code-f06fb8457049)
    * Not covering: Decorators
  * t-test applying Welsch correction

* [x] Detailed report - 7 min
  * Permutation principles
  * Different ways of representing, prefer per user
  * SQL Code, because Data engineering
  
* [x] Many A/A tests - 6 min
  * Code show running permutation, A/B test
  * Run one test, run many tests
  * What statistics for a battery of 10,000 tests
  * Pandas code processing
  * Code
    * Passing parameters

* [x] Possible issues and Statistical interpretation  - 7 min

  * What do issues look like and causes
    * Small samples
    * Skewed values and wide deviations
    * Correlation between IDs
      * Interference between visits
  * Interference not captured by a test

  * Why use t-test rather than permutation? Cost
  * Power analysis and detection curve
    * Twyman’s Law
  * Confusion Matrix

<!-- * [ ] Host a basic seerver
  * Assistance from DevOps, as exercise, low stakes
  * Run using one of many framework
* [ ] Create an interface
  * Python doesn’t have a lot of option, but you want autonomy
  * Button status change, always tell what’s happening
  * Connect to existing databases
 -->

* [ ] Many metrics - 6 min
  * Example has five because simple conversion funnel
  * Code
    * Parallel processing
    * Enum: clearly defined
  * Interpretation
    * Lead vs. lag metrics
    * Partial results, non-significant “trend”
  
  * Want a lot more:
    * Simple: basket size, consideration time, satisfaction
    * More complex: up-sell, retention, 
    * …
  * Understand which metric should be impacted
    * Lead and lagging, Health check 
    * …

* [ ] Categories - 6 min
  * Obvious ones: Country, day of the week

  * key variance: categories, filter, breakdown, values
  * Multiple comparison correction:
    *  Dunnett’s law

  * More relevant ones: previous engagement level, synthetic
  * Specialised:
    *  Travel: lead time to departure, duration, is_holiday
    *  Fashion: during season, sales, how feminine, style
       *  hard to find size, serious vs, costume
    *  Clinical: from metric to status, poly-symptomatic
 * "What’s in it for me?": judgement or insights


## Documentation

* [ ] Record Loom video for the project — 8 to 10 mins
  * [ ] Validate Loom account
  * [ ] Record separate videos
    * [ ] Intro and A/B test: 25 min
      * [ ] Intro and Plan - 4 min
      * [ ] Data generation and extraction if you have event logs - 7 min
      * [ ] First report and attribution - 6 min
      * [ ] A/B test - 8 min 
    * [ ] Permutations and statistics: 28 min
      * [ ] Detailed report and data re-achitecture - 7 min
      * [ ] Many A/A tests with permunations - 6 min
      * [ ] Statistical interpretation - 7 min
      * [ ] Possible issues - 8 min
    * [ ] Recommended Extensions: 26 min
      * [ ] Host a basic seerver - 6 min
      * [ ] Create an interface - 6 min     
      * [ ] Having Many relevant metrics - 6 min 
      * [ ] Including Categories and transform them - 8 min

* [ ] Written Documentation
  * [ ] Add images to documentation
    * [ ] Separate tails on realistic distribution

## Data sources

* [ ] Data processing
  * [ ] Separate attribution as a distinct event
    * [ ] Decide how the assignment works (uuid+exp_name hash)
  * [ ] Re-format data pipeline to use attribution logic
* [ ] Store values in parquet/arrow file

## Data processing

* [ ] Expressely list relevant columns, possible values
  * [ ] Check that those are present, portions are appropriate — or graceful alert
* [ ] Include formal language for the definition of metrics (dbt?)

## Code quality

* [ ] Object-oriented
  * [ ] Make page sequence into Enum — excluding assignments
  * [ ] Review class structure and dependencies
  
* [ ] Add tests
  * [ ] Fixtures for db testing https://docs.pytest.org/en/latest/explanation/fixtures.html

## Interface

* [ ] Fix interface
  * [ ] Show output as tables
  * [ ] Show progress of data generation, permutation processing
  * [ ] Pick start and end dates for each test
  * [ ] Export as CSV — with an alert
  
## basics.md

* [ ] Add illustrations
  * [ ] Separate tails on realistic distribution
  * [x] Illustration: p-value
  * [ ] Inverse Normal distribution

* [ ] Missing links
  * [ ] Second ghost of experimentation: Skyscanner

* [x] Missing passages
  * [x] Differences with $z$-test
  * [x] Welsh test with both variance
  * [x] Interferences
    * [x] Unit definition: Visitors coming back
  * [x] [Twyman’s Law](https://en.wikipedia.org/wiki/Twyman%27s_law): unlikely results

* [ ] Spell-check

## Other .md

* [ ] Multi-arm bandits
* [ ] Bayesian approach?
  * Implementation and principle
  * Picking a conjugate and relevant prior
  * [Expected value of information](https://www.linkedin.com/pulse/concept-evi-expected-value-information-ronny-kohavi/) and continuing the project while it’s still relevant
  * Relation with Bandits and Thompson sampling

* [ ] [Dunnett’s](https://www.google.com/search?client=safari&rls=en&q=+Dunnett%27s+test&ie=UTF-8&oe=UTF-8)