# Explaining how A/B-test works in practice

## How does an A/B-test works?

Imagine you are responsible for a service, say a website for pet adoption. You care about people booking a meeting to come visit and possibly adopt a stray. You have social-media outreach and key-word advertising to drive traffic, and you care specifically about the **conversion rate**: among the visitors who land on the home page, how many book a meeting.

To improve that conversion rate, you have an idea for an improvement: a cleaner page design or a more compelling call-to-action. You are not sure how effective it will be. The best way to do that is to **split** customers in two and show one half your existing set-up ('Control' or A) and the other half your modified, hopefully improved version ('Treatement', or B). If the improved version leads to a clearly better conversion, you probably want to adopt it.

Assuming you have logs from such a site, the code in this repository aggregates those to compute the conversion rates in both case. It compares the two using a $t$-test to decide whether the observed difference is large enough to be meaningful, what we call **statistically significant**.

Spliting the traffic to an on-line service and comparing conversion rates with a $t$-test is a univerally used approach to understand the impact of any change. In science, it’s known as a **random control trial** (RCT) but online services prefer to call it an **A/B-test**.

### Permutation tests for control

This code also uses the same sample to run a **permutation test** also known as a batch of A/A-tests. This meta-validation approach allows us to verify whether running an A/B-test is relevant and appropriate. It is a simple, convenient and universally valid way to detect issues with common assumptions made when running any statistical test, notably the stable unit treatment value assumption or [SUVTA](
https://www.sdu.dk/-/media/files/om_sdu/institutter/ivoe/disc_papers/disc_2020/dpbe3_2020.pdf).

It spite it being easy to implement, and the practice coming strongly recommended, it is rarely implemented. Hopefully, this code sample can help you implement it your own and learn from it.

## The goal of this repository is educational

This code is meant for **educational purposes** and should not be imported into production system without understanding the role of each component. 

This code is meant for education purposes and uses **simulated data**. The code also leverage the library [fake-web-events](https://pypi.org/project/fake-web-events/) to generate a synthetic event flow. For convenientce, it stores locally and can reload a dataset of events. We encourage you to edit parameters to match your own event flow, or rather to use the code sample on actual events to understand how A/B testing works for your company.

### What this codebase does not cover\

This codebase can’t cover every aspect relevant to A/B testing.

#### Bayesian approach

This code base takes a intuitive look at the most common form of test: the $t$-test. We do not discuss the difference between Bayesian and frequentist testing philosophies. There are a lot of examples online on how to run Bayesian A/B-tests. 

It’s reasonnably easy to replace the few lines of code that handle the $t$-test with a Bayesian update, or any alternative statistical appraoch. What mattered to us is to explain the basic data processing from web logs to results, and .

#### How to implement Feature flags 

To run an A/B-test on your own service, you need a control mechanism. This allows you to decide which visitor see what. Those are known as toggles or **feature flags**. Thanks to flags, you can expose half of your visitors to one experience and the other half to another. We strongly recommend this architecture to implement an A/B-test in production. There are alternatives like embedding assignment methods in the code. Those don’t allows to control overall releases like a feature flag does. Merging new features with an A/B-test makes releasing through an A/B-test seamless.



#### Experimentation and A/B test

Beyond running a single test, the practice is more widely known as **Experimentation**. That covers not just looking at the result of a test, but learning from it, and trying something better. In practice, most tests lead to non-significant results, so improvement and iteration is key. Another aspect of experimentatiin is the use of controlled test and non-controlled situation to run **causal inferences**. [Sean Taylor from Meta and Lyft gave a great presentation explaning how that fits with Experimentation.](https://youtu.be/5Myw5A-ZILs).

Experimentation also covers what to do in preparation of test (before and after surprising results): gather unstructured and structured feedback and synthetise those into **assumptions**. Those assumptions have to go from anecdotes to high-level pain-points like 

> “Visitors find the site confusing.”

then to more specific ideas and goals
> “With fewer buttons to pick from, users should navigate better.” 

down to detailed implementation:
> “If we hide [the less relevant options] in [this menu], the conversion rate from the homepage to the reservation page will increase.”

The tests are meant to confirm those assumption.

Organising an experimentation practice is gathering all opinions about the product and organising them. The commonly used internal communication support (documents, meetings) are the right tools for the job so we won’t cover them here. A/B-tests constitute the one step in that iteration loop that needs explicit software support.

# A/B-test principles

*This is an introduction to statistical tests. You can skip this section if you are familiar with the need for permutation tests.

How does an A/B-test works? What are its assumption and its limits? How can we test them in practice? 

## A/B-test without statistics

### Splitting traffic 

An A/B-test relies on a simple idea: to measure the impact of a change as fairly as possible, you want it it to be in realistic conditions and have all else be equal. On an online service (a website, an app, an API, a physical experienced controled by an online server) the easiest way to do that is
1. to split the traffic coming between two segments, and
2. expose each segment to one of each possible experiences: with the change ('Treatment') and without ('Control').

### Ratios and $t$-scores

By comparing the two, you can measure the impact of the change, free of most interferences. The most common way to represent the activity on a serivce like this is to see whether users go from one initial step to another, *i.e.* with **conversion rates** that together form a funnel. Because this is a very controlled experiment, it should be easy to tell which version has the most promissing conversion rate. In practice, some differences are small. How can we tell?

The most common way to decide if two ratios are significantly apart is with a statistical test known as a **$t$-test**. Before we cover how those work, we will explore a more intuitive approach: a permutation test. 

First, let’s …

### Split tests, aka A/A-tests

Imagine running an A/B-test but not changing anything. Essentially, running an A/A-test. It’s actually very easy to do: take the last weeks of activity of any service, randmomly split it in half, and voilà! That’s an A/A-test. You didn’t have to change anything in the past because both halves are meant to be identical.

You do not expect to see a significant difference but, because of randomness, there might be a small difference between the conversion rate the two halves of the traffic.

![Difference between the conversion rates of two random, presumably identical, halves of your recent audience](/docs/img/1_permutation_graph.png "Difference between the conversion rates of two random, presumably identical, halves of your recent audience")

Imagine doing that again, with the same traffic but a different split. You might get another difference, also negligeable in principle. Imagine doing that ten times. You start seeing what “negligeable” looks like.

![Distribution of differences in conversion rate between ten pairs of presumably identical random halves of your recent audience](/docs/img/10_permutation_graph.png "Distribution of differences of conversion rate between ten pairs of presumably identical random dichotomy of your recent audience")

Actually, that is still not enough to see a pattern appear. 

### Permutation test and Distribution tails

Imagine doing that a *thousand* times or more. Then typically, the pattern is more obvious: the A/A-tests measure a difference between the two “identical” halves that follows a **bell-curve**. Most of those differences are less than a certain quantity.


There’s no obvious maximum value that defines a clear-cut impossible value for that difference. However, we can define a threshold that is rarely crossed. We are tempted to consider that the small minority of the outliers are exceptional, the far ends or **“tails”** of the distribution. A common way to define those is to isolate the 5% of either extremes, the tails of both sides representing 2.5% of all random cases each. This 5% number is known as the **significance level**, noted $\alpha$ by convention. IT’s also called the “FPR”: we’ll look into that acronym in the second next section.

Separate tails on realistic distribution

Let’s consider the thresholds that separates those tails from the bulk of the distribution. Because we can permute each half, the distribution should be symetrical. More exactly, with more and more random example, it tends toward being symetrical around zero: no difference. So are the bounds: if we try enough times, the lower and higher threshold will be ± the same value.

By construction, in an A/A-test, crossing those bounds is unusual. It is not impossible, but it’s **unlikely** to happen.

## Measuring outliers with the $t$-score

### Contradicting the Null hypothesis

That is the intuition behind the most statistical frequentist tests:
* if we **assume** there were no **actual** difference between A and B, then a difference larger than that threshold would be **unusual**;
* therefore, when the difference is too large, outside those bounds, that assumption leads to unlikely conclusion.

The common phrasing can seem convoluted: the first point is known as “the Null hypothesis” and that conclusion is presented as “rejected”. That turn of phrase is key though, because it doesn‘t actually guarantee that we can idenfity any difference, or that what we measure is real: it simply says that it’s unlikely the two things that we are measuring are similar.

### Positive and negative results

In practice, those cases with a statistically significant differnce are deemed **positive** because they are considered having a positive identification of a difference.

This introduce confusion because sometimes the difference is negative, sometimes a negative number (say, ratio of complaints) is a good thing, therefore changes that benefit the business are called “expected” and the opposite are “inadvertent”. 

Following the same logic, “negative” results are not cases where the difference has bad consequences, but when the test is unhelpful: the difference measures is not statistically significant. Many people summarise that saying there are “no difference at all” which is patently false (unless the exact value is precisely zero) but it’s more likely (although not certain) that the difference is **too small to confirm**.

### False positive rate

For now, let’s go back to assuming that we ran a test with no actual differences. Using the convenion we just introduced, that means that we can expect it to have **negative** results, i.e. no significant diffence. Is that always the case?

Rather than one, let’s say we run 100 A/A tests. How many of those will lead to you to rejecting the Null hypothesis? By construction, 5 of them? Roughly: in practice, each of them as a 5% chance of being positive, so 5 is the most likley, but it’s possible to wee 4 or 6 because of random chances. With 10,000 tests, we should always be between 480 and 520.

Either way: we expected 10,000 negative, but had a about 500 false positive. By construction, the ratio between those two numbers is $\alpha$, which is why $\alpha$ is often called the False positive rate or FPR.

Many people read this and assume that this means “If my result is signifciant, there’s a 5% change that it is not real.” That is not what $\alpha$ is. $\alpha$ means: “If there is no difference, there’s a 5% change that I will detect something by mistake.” The two are very different concepts. Why so many people confuse them is strange when you go through that construction.

The ratio that people want, “How many of my positive results aka discoveries are real?” is known as the False discovery rate. We’ll come to it soon when looking at the [confusion matrix].

### $p$-value

One of the most controversial value when running that test is the p-value. We can define it very easily with the graph that we already have: After 10,000 A/A tests, how many of them give more extreme value than what we found?

Illustration: p-value

Let’s assume the test is on a large population. Let’s also assume that the effect is clear and strong. there is no chance that any random A/A split will ever come close to measuring the same effect, not even one in a million. Then the $p$-value is extremely small, less than a millionth. 

It might even not make sense to define it with millions of permutation. We’ll come to that in the next section.

On the other hand, a $p$-value up to 0.1 or 0.2 means that the difference that we measure is unusual, but not exceptional. Anything larger doesn’t mean much. There are no real information to infer between a $p$-value of 0.3 and 0.9.

## $t$-test and statistical abstraction

There are two issues with using permutation as a way to define an A/B test:

* running so many tests can be consuming, especially with many permutations;
* we remain dependent of randomness, especially with few permutations.

### Great Number Theorem

Thankfully, after running tests like that, stasticians have noticed, that given a handful of basic assumptions a few things are true:
1. with enough measurements, result follows a bell-curve;

   That distribution has always the same shape, but two parameters:
   * an **average** or mean noted $m$ or $\mu$ and
   * a width also known as the **standard deviation** noted $s$ or more often $\sigma$;
2. the bell-curve tightens if you run the simulation on larger population; here, ”tightend” means that the average stays the same, but the standard deviation reduces predictably.

That result is known as the [Great number theorem](wikipedia). It applies to any measurement, not just A/A-tests. If we look at many samples of visitors, and consider the ratio of convertion, $\mu$ is the overall conversion rate. But if we look at the difference between two identical halves, then $\mu = 0$ 

With several dozen visitors, the bell curve follows a Student’s $t$-distribution. With many more visitors we end up having a very accurate view of $\mu$. The Student’s distribution then becomes very close to another bell curve, the Normal or Gaussian distribution. 

The difference between the two is not very important for an introduction, but remember that with a many visitors, [the two converge](https://www.jmp.com/en_us/statistics-knowledge-portal/t-test/t-distribution.html). Essentially, if you don’t know the exact value of $\mu$ before starting you have to use an estimation based on your sample. There’s a small chance that this estimation is off by a bit, therefore because of that uncertainty, the difference that you measure could be further out.

If you have a large enough sample (more than 30 is conventionally “large”), you can ignore that gap and use a Guaussian distribution as a reference. This is known as a $z$-test because in addition to being called “Normal” and Guaussian, it’s also known as the $z$ distribution.

### Standard unit testing validation assumption

Technically, the assumptions are that each visitor has to be “i.i.d.” act independently of each other (otherwise interference make things complicated) and all follow the same behaviour pattern (that last one is not essential but part of the standard version of the theorem). The expected outcome also have to be “bounded”: having some visitors contribute extreme values make the result slower; that last one is guaranteed when looking at conversion rates, not necessarily so when looking at revenues.

Another approach frames similar assumption differently: it specifically considers that there are units, split between two groups and it considers how those two groups interact. Similar asusmptions become the Standard unit testing validation assumption, or **SUTVA**. Essentially, the idea there is that somethign that affects one half shouldn’t affect the other half. It’s the important part of the “independence” previously mentionned.

If that is true, we can expect comparable results: a bell-shaped distribution of differences, centered around zero. What matters is that this cloud of uncertainty shrinks if the size of the samples increases.

### Bell-curves

The bell shape doesn’t have a clear, sharp edge, but it has a bulk contained within a finite segment. Assuming the sample of visitors is large enough, we can expect the distribution to follow a known curve, the Guaussian distribution. This means that we can use a standard function to measure how far a certain $p$-value is from the mean, in units of standard deviation.

[Illustration Inverse Normal distribution]

The standard deviation is the distance from the mean to the inflection point. This is not the limit of the 5\% theshold. Either tails (each representin 2.5\% of cases) start at about twice further.

* inv_Norm(0.500) =  0    because the mean is at the center of the distribution;
* inv_Norm(0.025) = -1.96 which means the 5% theshold is almost two standard deviation away;
* inv_Norm(0.975) =  1.96 which means the 5% theshold is almost two standard deviation away.

### The signal and the noise

That margin of a few “standard deviations” is where a difference might happen by accident. This is where a gap is not meaningful is the core concept in statistics. It’s often vulgarised as the **noise** as opposed to the **signal** a meaningful difference —— either larger or in a context with less noise, say, given a larger sample.

Almost all the efforts of statisticians and data professionals are to reduce the noise, in order to improve the signal.

Without abetter signal, an organisation might be comfortable making decision based on differences of only one standard deviation rather than two. That increases the risk of making decision based on flukes. 

### $t$-test statistical logic

This means that if you are looking at a large sample of user sessions, you don’t need to run thousands of permutations tests to figure out where the A/A-test results will fall. You only need two numbers: the typical conversion rate $c$ and $N$, the number of participants in each half.

The expected difference between indentical halves is null, therefore the average of the distribution is zero. The standard deviation gets smaller with larger sample:

$$\sigma = \sqrt{\frac{c\times(1-c)}{N}}$$

Those two numbers are enough to estimate what the bell curve would look like, and where an outlier would be.

Finally, we can take the measured difference between both ratios $d$ and compare it to $\sigma$ to tell if it is exceptional or not: the ratio is known as the **$t$-score**. A $t$-score of 2 or more is considered significant at the 5% level because it’s more than 1.96. So would a $t$-score of -2 or less. In practice, it’s common to talk about ±1.96 $\sigma$.

With an $\alpha$ different from 5%, the threshold of 1.96 would be different.

* [ ] [table with common inv Norm score](…)

A $t$-score and a $p$-value describe the same standardized difference. However, $t$ tends to be a more intuitive metric. Therefore, we would recommend to express results using that value: “We observed a difference of 12%, which is *three times the standard deviation* given the test condition. That’s therefore a significant result.”

Expressing the same idea as a $p$-value requires to introduce the convoluted counter-factual assumption “If there were not a real difference adn this gap due to chance, that could only happen .3% of the time.” If you can articulate that salad of words properly, good on you; still, in practice, your listeners tend to skip the nuance and assume you over-complicated the more simple idea that “There is a .3% chance that this was due to chance.” Human psychology has proven very attached to this particular mistake.

We’ll explore later how to compute an answer to that distinct question: How likely is a sigificant result real? It’s a legitimate question, but one that needs one extra variable.

### The most common actual test: Welch’s test

There are more small nuances in practice.

The definition above assumes that there is one well-known conversion rate and both halves have had the same exact number of visitors. That’s not always the case. In practice, conversion rates are seasonal and depend on a lot of changes happening simulataneously, like the press covering a related topic or outages. You might not be able to reliably use recent average to estimate it. Therefore you might have to use the conversion rates *during* your A/B test to estimate the two key parameters. 

Instead of that simple formula, we typically use the conversion rate and number of visitors for both A and B into a combined formula. That is known as the [Welch’s test](https://en.wikipedia.org/wiki/Welch%27s_t-test):

$$\sigma = \sqrt{\frac{c_A \cdot(1-c_A)}{N_A} + \frac{c_B\cdot(1-c_B)}{N_B}}$$

From there, you can normalise the difference with $\sigma$ and apply the same $t$- or $z$-test.

### The number of visitors and the number of A/A tests

Note that with a hundred visitors, we won’t have a very accurate tests. Even so, we can run millions of A/A tests and have a very precise idea of how inaccurate those tests would be. That would be computationally expensive, which is why we typically prefer to use statistical formulas. They make the work of estimating the actual standard deviation of one test easier.

That is true, *if* we can make the aforementionned assumptions. This is why we still recommend to run A/A tests. It would be expensive to run millions, just to have an accurate idea of the noise. But we can run a few thousands to estimate whether some statistical properties emerge. There are essentially three things that should be manifest after 1,000 to 10,000 permutations:

1. the number of significant tests should match $\alpha$.
2. the distribution of $p$-value should be uniform
3. the standard deviation of all the differences should be close the formula expected below.

!["Example distribution of $p$-values on 10,000 A/A-tests with independent visits"](img/p_values.png "Example distribution of $p$-values on 10,000 A/A-tests with independent visits")

We wouldn’t recommend to use measurements from a 1,000 A/A test for your analysis: the statistical formulas are more convenient and typically more accurate.  However, if the two visibly diverge, you know that something meaningful is wrong.

### Detecting exceptions

The issue is that the basic assumptions (SUTVA) are not always true. In almost every company, people just assume that they are. If they are not, you will need professional statisticians to help you go around the issues. Typically, they are true for some metrics and some units but not all.

The point of this first exercise is build a simple test to check if the permutation case and the statistical approach match. If they are not, a statistician might would want to investigate.

## Reasons for not matching theory

We mentionned earlier that this theoretical description might not match long sequence of running permutation tests because some assumptions might not be true. You can see those as the conditions for the Large number theorem, or the Standard unit testing validation assumption or SUTVA.

The theoretical assumptions are relevant here but let’s remain practical. Why are things that, in practice, assumptions that a $t$-test makes that are not always true?

### Small samples

A small number of visitors means that we can’t apply the large number theorem with the same confidence.

The number of permutation that we run isn’t very relevant: we need a large number to get to a recognisable bell curve. There’s no constraint on that. However, with a very small number of visitors (say, under 30), there is a finite number of permutation possible. That can be a problem because those might not be enough to define a bell-curve. It certainly is a problem because that curve will have a very large standard deviation and very low power.

### Skewed values and wide deviations

Not all metrics are conversion rates: another common type of metric is the revenue per purchase or (adjusted by the conversion rate) per visitor. In that case, each visitor is not converted or not, but some bring a lot more revenues than others. If one important client (what casinos used to call “a whale”) is randomly assigned to one group or another, they might single-handedly flip the test. If there are a few of those and they represent a large part of the overall revenue, then the bell curve might not have the expected shape: there might be many A/A test with more unhelpful, skewed results. The distribution is said to have “fat tails” because those extreme cases are more common than expected.

There are cases where the core metric is very skewed but we are not interested in the average. A common occurence of that is latency: how much time, in microseconds for a page to load, a server to respond, an error to be detected, etc. For such metrics, the average isn’t as representative of an issue. Problems are rare. What matters are the slowest cases. A common way to synthetise is therefore not the average but the 95th or 99th percentile. Those cases should not be dealt with a $t$-test. [Mann and Witney have defined a $u$-test that makes more sense for those.](https://en.wikipedia.org/wiki/Mann–Whitney_U_test)

### Interference between visits

A more common but more subtle issue is if different visitors, or visits are not independent. This depends more specifically on whether your implementation treats the same person coming to your service multiple times as different or not. Web browsers have cookies that allow to match two successive sessions and offer consistent experiences. Privacy tools, applications, different devices complicate things.

In those cases, you want to be very specific about what exactly is the **unit** of your test: a person, a websession, an account, a cookie, an organisation or a combination of some of the above.

There are also similar interference between members of the same household: if a supermarker sends distinct promotions to each member of a **couple**, the most generous rebate will be used to buy the family’s groceries that week. That leads to over-estimating of the impact of the same promotion if it were send to everyone uniformly.

Many services that offer travel, fashion, home design, beauty products, even real-estate typically have longer **consideration** period, accross several sessions. If you expose users to different experience at each session, the same users will be influenced across session. This might not be obvious, but certain test configuration, certain objective metrics and units, lead to failing their A/A test, see the [second ghosts of experimentation](…) for an example about how the anti-correlation of conversion rate between successive sessions had a measuable impact.

### Assignment consistency and picking the right unit

Before running a test, we want to decide how to split traffic. Should the same user coming back within a session, or hours later, be exposed to the same experience, for **consistency**? This is especially relevant if you expect your changes to influence decisions that might take weeks or months. 

If you are running a recommendation system or a content-generation tool, variation from one query to the next is expected, so you can ran experiment where every _query_ has it’s own distinct assignment. If you are testing promotions, inconsistency won’t be appreciated, so a _household_ should be assigned to one group.

If you are testing an algorithmic tool that will decide which worker within a specialty domain is going to handle which task, then you can’t assign per worker: you have to randomise the _whole queue_ of task as one **unit** — at least for a certain period of time.

### Sample ratio mismatch (SRM)

Another possible issue is to make sure that the ratio of customers exposed to each experience is what you expected. Practitionners recommend to split fairly or 50/50: it’s not necessary but it allows to maximise the [test power](#power_analysis). We’ll see later what that means. With a large audience and two options, it should not be a concern. However, the idea of an A/B-test can be augmented to have more than two options and compare many version of a feature. This is known as an A/B/C-test or, if it has more than three option, an A/B/n-test.

If you only care about the immediate reaction to, say, recommendation or a search result, then that consistency accross session might not be important. It is important to be able to match a result with what users pick. Therefore, **attribution** is still necessary. There are many ways to handle attribution, from sending the assignment with every event (what we assume here) to reconstructing by having each event assigned to a user, and have assignement event matched to each user after the fact. Both approaches have their limits. We’ll explore that later.

### Interference not caputed by a permutation test

This is not always detectable by a a permutation tests.

Another common issue is when users communicate. Say you offer a coupon to individuals. If two spouses share grocery duties, but only one gets a coupon, then they might use it for items that their spouse would have bought otherwise. That skews your results further.

# Test validation

Running a test in isolation often isn’t enough. Before running a test, you want to make sure that the circumstances will allow you to drive relevant conclusion. After running many tests, you also want to make sure you understand the compromise that statistical testing presents.

## Power analysis

The first thing to do, before running any test is to estimate how _precise_ a test is, whether it can detect a change as small as what we expect. This is known as the **power** of a test. If “power” and “precision” sound contradictory to you, think of it as a microscope.

### Minimum detectable effect

Given the standard deviation $\sigma$ of a test and the significant threshold $\alpha$ that we pick, we can define the smallest measured difference that would be considered significant: $\sigma\cdot\alpha$. That's the minimum detectable effect (MDE).

Note: the MDE is not an exact thereshold. Because of the noise inherent to the process, we will measure something slightly different. Therefore, we can’t consistently detect a difference that small. We might detect it half the time, when we randomly measure a larger effect than that. 50% is not **reliable**.

To know what is the smallest difference that we can reliably detect, we need to decide how often is “reliable” and go back to the permutation test.

### Power analysis

Another key information that you can gather from running many A/A-tests is the likelihood of detecting a change of a given size. We know that testing no change has a 5% (false) detection rate, by construction. 

### Impact curve

If we introduce a small difference, if B is a little bit better than A, then it has more chance of being detected than 5%, but how much? Well, using the distribution of permutation tests, we know that some A/A tests were close to that tail. 

![A/A-test liminal cases](/docs/img/liminal_aa_cases.png "")

If we represent the **cumulative curve** of A/A tests, there’s the 5% false positive and 1, 2, 5 more percent that were close. Let’s expand that logic and draw the whole cumulated distribution.

![Power curve](/docs/img/power_curve.png "Power curve")

That way, we can represent the probability of a change being detected, based on how large the change is. No change is 2.5%, by construction. Massive changes are 99%. But no change seem to be large enough to be detected 100% of the time. Therefore we need to decide how likely detection has to be to be enough.

### Detection threshold

The convent is to decide that if a change as an **80\% chance** of being detected, that is reliable. That number is known as the power of an experiment and it is conventionally noted as $1-\beta$. 

![Power curve with threshold](/docs/img/liminal_aa_cases.png "")

In practice, $\beta$ is the likelihood of not detecting a large chance, and is known as the false negative rate (FNR).

Both $\alpha$ and $\beta$ are set by **convention** and both can be modified to adapt to circumstances and standards of your institution. Theoretical physics famously has an $\alpha$ at 0.000000197%, corresponding to *six* standard deviation. A tigher significance threshold like that will make significance hard to reach unless you have very compelling evidence. It makes sense for science but might not for most industries. A higher burden of proof is understandable when the conclusion are major. Otherwise, it slows down exploration.

Unlike $\alpha$, picking a $\beta$ won’t influence your individual testing process. Picking a $\beta$ let you estimate how large an impact has to be to be detected. No matter what, you have more chance of detecting a larger impact and less chance of detecting a small one. Measuring the power of your test at a conventional detection level will let you know whether a test is likely to detect something, given the changes that you expect.

A low or weak-powered test is one where the power curve climbs slowly, only able to detect very large, unlikely changes. If that's your case, it might make sense to consider alternatives to A/B-test.

### Twyman’s Law

Setting realistic expectations of impact is key: a test with a low power is also a test with a lot of noise, i.e. one where a positive difference is likely due to chance, moreso than possimistic expectations. That makes positive results of a test with a weak power inherently suspicious.

Counter-intuitively, if you have a weak-powered test and you see an unexpectedly large difference, the probability that this is a fluke is higher as the effect is larger. If you did not expect a large change, a surprise might be a fluke. This is known as [Twyman’s Law](https://guessthetest.com/the-winners-curse-the-big-problem-with-enormous-winners-in-a-b-testing/
https://en.wikipedia.org/wiki/Twyman%27s_law).

In those cases, the recommendation is always to improve the test power. That likely means running a test for longer, possibly on a different sample. Detailed analysis and user interviews might be required: a big surprise means there’s either a mistake to isolate or something important to learn.

## Confusion Matrix

So far, we have covered that a test can be positive (detect a significant change) or negative (no statistically-significant change). We have covered that, if trying enough tests without actual change, some can be detected as significant, aka false positive, the $\alpha$ significance threshold. We have also identified that if a change is small or if we are unlucky, a test might not detect those, the $\beta$ power threshold.

We can combine those two numbers into a matrix that will allow you to understand the key number that your stakeholders actually want to know: the **False discovery rate** (FDR), i.e. among my results deemed significant, how many are flukes?

### Examples with five hundreds tests

To make more sense, this matrix require some scale, so let’s assume that you have ran hundreds of tests. It starts making sense after a hundred, but for the same of convenience, let’s assume we ran 500.

#### High success rate

Let’s imagine a great outcome where 40% of those were positive, i.e. we detected significant effects. That is actually a very high number for the industry. In an idea world, that would mean that 200 are actually positive and 300 were actually negative"

||Actually <br> positive|Actually <br>  negative|
|-|:-:|:-:|
|Tested <br> positive|200|-|
|Tested <br> negative|-|300|

In practice, we know that if we have 300 actually negative tests, $\alpha$ of them, or 15 will appear significant. Because we have observed 200 signigicant test results, then we can assume 15 of those are flukes. We don‘t know which one, but it’s probably between 12 and 18.

||Actually <br> positive|Actually <br>  negative|
|-|:-:|:-:|
|Tested <br> positive|185|15|
|Tested <br> negative|-|300|

Similarly, if we test about 200 actually positive changes, $\beta$ of them, or around 40 would not test well. This means that they woul appear negative, but be actually impactful changes.


||Actually <br> positive|Actually <br>  negative|
|-|:-:|:-:|
|Tested <br> positive|185|15|
|Tested <br> negative|40|260|

That table is an estimation. A lot of things can make it more complicated, like the distinction between a weak and a strong change. However, it offers what neither $\alpha$ or $\beta$ alone can tell: a way to compare the number of falsely positive to all positive test.

In this case,
$$\frac{15}{15+185} = 7.5\%$$

Another common question is whether the test can detect good ideas, or are impactful change ignored by the process. In this case, the ratio isn’t too high either.
$$\frac{40}{40+185} = 17.8\%$$

Why a very high rate of success of 40\% and conventional FPR and FNR, we can reliably trust most tests results: most of them are real.

#### Low success rate

What happens if we have a more common success rate of, say, 10\%?

Then the matrix looks a little different: we only observe 50 of 500 tests appearing positive.

||Actually <br> positive|Actually <br>  negative|
|-|:-:|:-:|
|Tested <br> positive|50|-|
|Tested <br> negative|-|450|

but we know that 5% of the 450 negatives, so somewhere around 22 or 23 cases would appear as positive, while 20% of the 50 positive tests, so 10 would appear as negative. This means the matrix looks more like this:

||Actually <br> positive|Actually <br>  negative|
|-|:-:|:-:|
|Tested <br> positive|27|23|
|Tested <br> negative|10|440|

The two ratios that we are concerned about are a lot more alarming: 23/50 so almost half of the positive results are probably flukes, while 10/37 so almost a quarter of the good ideas are overlooked by the test.

This illustrate why, to compute the false discovery rate, you don’t just need $\alpha$ and $\beta$ but also the **ratio of positive to negative observations** in your program, sometimes called the dicovery rate.

### Learning and discovery rate

The reliability of A/B-tests doesn’t just depend on the settings of the test, but of the overall experimentation program and how good are ideas in general. The goal here is not to improve the success rate by tweaking $\alpha$ or $\beta$, or even running tests for longer to gain power at the expense of speed. The goal is to **learn** more about users. By knowing them well and trying different things, we can develop a consistent view of what they expect. With that, we can develop better suggestions and maintain good ideas, even after trying obvious improvements.

There’s one small issue: an A/B-test doesn’t teach much. It just say whether an idea was likely to be good. The sign is not very reliable and the amount measured imprecisely. How can we learn from a noisy signal like that?

In the next session, we’ll explore how we can leverage experimentation to **learn** about users.
