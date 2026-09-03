# Data generation

This demonstration cannot rely on sensitive commercial data to reliably demonstrate different phenonema that A/B test can encounter. Instead, we use synthetic data that has the characteristic that we expect to see from most organization using a web site as their main activity hub. 

How do we generate synthetic, realistic web logs at scale? We use the library [`fake_web_events`](https://pypi.org/project/fake-web-events/) that recreates web events based on a handful of parameters.

## Simulation parameters

To recreate a realistic sequence of log events from a webpage, we need the structure of that website and the expected flow through it. We also need how many users we expect, and at what time of the day they generally come, as well as which browser they use and which part of the world they are comin from.

### Session flow

We start from a list of all **pages** on our imaginary website and a description of how users might go from one to another. This is a directed **transition graph**. It includes a _Start_ node that precedes all pages that users might land on from external links, and an _End of session_ that user can reach from any page.

All those internal transitions have a likelihood. For instance, it’s likely that a payment will work, so the transition from Payment to Confirmation is high. Those are standardised to add up to 100\%, including the _End of session_.

Here is the example that we use for our Control traffic: 60\% of our traffic start from the homepage, 25\% from the description of Product A, 15\% to the description of Product B. No other page can be reached from outside the website.


````mermaid
graph TD
  a((Start)) ==0.6==> h[Home]
  a --0.25--> p_a[Product A]
  a --0.15--> p_b[Product B]
  
  h ==0.45==> h 
  h --0.17--> p_a
  h --0.12--> p_b
  h --0.26--> x((End<br>session))

  p_a ==0.5==> p_a
  p_a --0.18--> h
  p_a --0.12--> c[Cart]
  p_a --0.2--> x

  p_b ==0.4==> p_b
  p_b --0.22--> h
  p_b --0.14--> c
  p_b --0.24--> x

  c --0.25--> c
  c ==0.5==> p(Payment)
  c --0.15--> h
  c --0.1--> x

  p ==0.45==> p
  p ==0.4==> f(Confirmation)
  p --0.1--> c
  p --0.05--> x

  f --0.4--> f
  f ==0.6==> x
````

Note that the same page might be visited multiple times in a row, or re-loaded. This is common for the payment page, in case of a payment for instance.

### Time of day, number of users per minute

Users are more likely to open their session at certain time. The library we use allow to configure that too. When calling the traffic generation, we can define how many session we expect to see per day. The two are combined to define how many session we can expect at any moment. That library doesn’t allow to confugre explicitly for yearly pattern.

We also have a randomized, realitic delay between two page loads. Those, combined with session of randomized number of pages, add up to realistic session event logs.

### Number of users 

Users are only represented by their UUID (Universal Unique Identifier), a common standard to use randomised, non-consecutive ID over 128 bits. Given the length of the string, there is a vanishingly small risk that two users randomly have the same ID.

Our configuration allow us to define a number of distinct users. In practice, with few users and very active websites or for long data samples, the same ID might be used for several session. This allow us to represent returning users.

However, this simulation doesn’t have an explict way to make satisfied customers more likely to return, or even simulate satisfaction.

### Browser, region, etc.

There are options to create realistic-sounding names, phone numbers, postal addresses, etc. using the library `Faker` but that aspect isn’t as much a focus for us. We do use the devices and country in our effort to explain the role of Categories.

### Generation session

The approach used by the library is to generate data continuously, starting from the current date and accelerating in time faster than calendar time. That way a session only several-minute-long can generate reaslistic data over months in the future.

If you want to use large samples, say for more powerful A/B tests, you are welcome to run the data generation methods for longer.

## Managing variants

In order to generate more than one version of the flow, but have measurable differences between two possible variants (Treatment and Control), we actually generate them separately, using separate folders `control` and `treatment`, each with their distinct, local `config.yml` files. The two versions are later merged into a single sequence of events.

This means that we can modify any aspect of the data generation, from the time of day people connect to the probability of re-loading the payment page.

### Assignement

There are two types of set-up to decide whether a given user is explosed to chich variant: implicit or using a distinct assignement event.

#### Implict assigment 

The easiest way to is to store the assignment as part of every web event log. This is easier. Some feature flag and A/B testing solution are tightly integrated into the analytics pipeline and might be able to handle it that way. We can easily do it with a simulation.

#### Initial attribution event

However, that is rarely how things are done in practice. It’s easier for the assingment to be another web event. Typically, it is the first thing that a user sends when they connect to a website, as they load their first page.

This means that the reporting process has to match every event to the precedent assignement event.

### Contradictory assignment

If a user is assigned to Control once and to Treatment later, how can we know which assignement is relevant?

In practice, if a user conects twice with the same ID, they should be assigned to the same variant, so having two assignment events isn’t likely to contradict itself. It might happen though. It does before and after a A/B test is started, ended or extended. This is rare if we take into account A/B test schedule and every user uses the same identification principle.

However, if users can connect to an account mid-way, merge indentity through a session, it is common that they have two indentification source. In that case, one assignment might contradict the other. If you are testing, say, a promotion as Treatment, a user who reached a website might:
1. see the promotion on the home-page, be interested;
2. connect to their account that was assigned to Control; and
3. notice the promotion vanish.

Such cases are typically hard to handle well systematically.

### Contradictory assignment

Contradictory assignment, avoiding a user to see two variants, is related but slightly different than contradictory _attribution_, the same issue when processing data for test results: users who appear to have been assigned to both variant.

#### Simple solution to contradictory attribution: exclusion

The most common solution for contradictory attribution is to **exclude** those users. When dealing with mobile traffic, messages between an on-line service and the local app can be delayed. Contradiction at the edges of a test (Start and Stop) are common. It’s conventional to keep the last assignment as the valid one, and only exclude cases where the assignment goes back and forth at least twice.

Exclusion works if the cases are rare, but it’s not always marginal—not among the most active users, for example. This risks limiting test power and representativity. It also doesn’t address the user experience of contradictory assignements. This is why 

#### Avoiding contradictory assignment

Another approach is to separate experiments into two types:
1. changes that can be seen by all (that uses browser-based identification) from
2. changes that only apply to logged-in users (that uses account information).

That doesn’t cover experiments that promise benefits to account holders before they log in, not if they use multiple devices.

A third approach (after exclusion and having strict experiment type) is to have a **soft log-in**: returning users should still have relevant cookies on their browser. A mobile connecting from the same IP as a desktop might be the same person. A front-end service can make an educated guess of which account is likely a visitor’s. A visitors might return to a page whose URL contain a unique transaction ID. Those elements might not be secure enough to give access to view or edit sensitive account information. They should be enough to override a randomized assignment. That way, visitors see contradictory user experience less often, until they log in securely.

In practice, making sure to carry consistent assignment across distinct idenfitication namespaces (browser, app, account) often leads to complex rules and unexpected behaviour.

### Attribution to many tests

A more realistic set-up is to have every user assigned not just to one active experiments, but every experiment running on the site. On a very large and actively developped service, that can be thousands at the same time.

To handle those, you can either have:

* One large assignment event that has **all the variants** for every new users, typically stored in a dictionnary or a JSon blob with the name of each experiment as key and the variant assigned as value. That can be hard to read, but is typically parsed well, assuming your web event processors can handle objects that large.
* Separate assignment events for **every experiment**. That can generate a lot of activity, more the site itself. Typically, web-log processors like messaging queues are designed to scale to a lot of activity so it’s less likely to break data engineering expectations.
* A **separate service** or method outside of the typical data processing that, given a UUID can recreate any assignement. This is very useful, but has two issues:
   * If that service uses computationally expensive random functions, it can be more expensive to run at scale that to store the first assignment
   * By having the assignement re-run, we risk having inconsistencies. For example, if an experiment stoped running, the service might now assign every user to Treatment. A assignment recreation method would have to handle such changes.

* [ ] We have decided to represent multi-experiment assignement using the … method

#### Delayed assignment

All those assume that every visitor is part of every experiment being ran.

A smarter approach would be to have the assignment only counted when the customer is exposed to a meaningful difference in what they can see: when comparing two payment processors, no need to compare the difference between visitors who only reached the home page. Instead, an A/B-test that only looks at users who have reached the payment page where the difference is visible will be more relevant.
