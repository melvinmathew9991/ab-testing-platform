
[This introduction](docs/intro.md) is meant to present the rest of the documentation.

[Basics concepts](./basics.md) covers the common presentation of A/B testing, how to understand the role of statistics. It also explains why **permutation tests** are a simple and effective tool to determine if common testing assumptions apply.

However, common A/B tests can judge an idea, but they are often not enough to [learning from](./learning.md). To help with that, we explain how to define a set of **metrics** and breakdown activity in relevant **dimensions** are key to improve a service using A/B tests.

Secondly, a common recommendation and a frequent concern of people new to experimenation is [running many tests at once](./multivatiate.md). We explain how that works, why you should do it almost systematically and how to detect rare but possible issues. On top of that we explain how to [monitor tests automatically](./monitoring.md) without risking too many **false positive**. Both of those will help reassure stakeholders and encourage them to run more tests.

Finally, for more advanced users, we talk about [further test refinements](./refinements.md) around possible data issues.

[suggestion]: <> (Multi-arm bandits)
[suggestion]: <> (Bayesian and picking a prior)

One particularly interesting use case is too consider testing **recommendation** systems (search engine results, home-page suggesitons, targeted offers, etc.) using the [interleaving](./interleaving.md) approach.

For successful companies with large event databases, processing at that scale can prove expensive. To help handle those case, we cover approaches to [optimizing the computation](./optimization.md) of A/B test results.

Finally, we want to make sure we cover the importance of [running an experimentation program](./program.md). You want a visible effort to train, engage teams and empower both senior executives to drive the change, but also empower stakeholders with suggestions to be heard.


[pre-requisite]: <> (Feature flag)
[pre-requisite]: <> (Event logging)
[pre-requisite]: <> (Authentication/session)
[pre-requisite]: <> (…)

[bare minimum]: <> (Attribution & Exclusion)
[bare minimum]: <> (Agg. & Metric definition)
[bare minimum]: <> (Double-attribution excl.)
[bare minimum]: <> (t-test)

[necesarry]: <> (Permutation tests)
[necesarry]: <> (Categorical — causalQuartets https://twitter.com/JessicaHullman/status/1629150627937804288)

[necesarry]: <> (Cuped)
[necesarry]: <> (Multi-metric)

[essential]: <> (Damage early warning, cutoff)
[essential]: <> (Sample ratio mismatch)
[essential]: <> (Multi-comparision correction)
[essential]: <> (Sequential testing)

[always useful]: <> (Hold-out: custom split)
[always useful]: <> (Regression parameters)
[always useful]: <> (Multi-variate effect)
[always useful]: <> (Temporal analysis)

[generally useful]: <> (Delayed metrics)
[generally useful]: <> (Monte-Carlo simulation)
[generally useful]: <> (Scalable compute cell)
[generally useful]: <> (Holdback support)

[convenient]: <> (Time to significance)
[convenient]: <> (Ineffective flags remains)
[convenient]: <> (Color-coding, ranked results)
[convenient]: <> (…)

[circumstantial]: <> (Clustered, Des Raj corr.)
[circumstantial]: <> (Network cl., excl.front.)
[circumstantial]: <> (Multi-arm bandits)
[circumstantial]: <> (Interleaved tournament)

[different approach]: <> (Bayesian, dif priors)
[different approach]: <> (Additonal value info)
