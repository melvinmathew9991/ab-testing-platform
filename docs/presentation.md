---
marp: true
theme: gaia
#class: lead
class: invert
paginate: true
backgroundColor: #fff
backgroundImage: url('https://media.istockphoto.com/id/1294603953/vector/abstract-black-stripes-diagonal-background.jpg?s=612x612&w=0&k=20&c=nQZHTk-o97cNVqWnUe8BJg0A5jQG0tqylquzbt9YtcQ=')
---

![bg left:40% 80%](https://cdn-icons-png.flaticon.com/512/4403/4403291.png)

# **A/B _aka_ <br> Split testing**

How to process event logs
to decide the results
of an on-line experiment
with Python 

---

![bg right:40% 90%](https://s3-us-west-2.amazonaws.com/oww-files-public/3/38/Bacteria_3.png)
# Why simultaneous traffic spliting?

* Separate the **impact** of each idea
* Interference & possible controls
* Randomised control at scale
* Constraints: planning, ethics

---
# Experimentation

![bg left:45% 100%](https://wac-cdn.atlassian.com/dam/jcr:0684d7c4-6553-4d11-8af0-14462569d0f7/Feature%20Flagging%20Diagram%20-%20Desktop.png?cdnVersion=846)
* Feature flag & Control pannel
* Staged releases, “Test in prod”
* High failure rate, therefore:
  learn & iterate—also: retract


---
![bg right:40% 95%](https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQiz4yYu12ROtqzf6nWfsO8n3AEkmPxC1JFng&usqp=CAU)

# Buy vs. Build

* Foster an informed, engaged
  organisation-wide practice 
* Understand challenges
* Either way, many key features :
    * Integration to report metrics
    * Multi-comparison / Sequential 
    * Impact model: Bayes., M.-Carlo
    * Multi-arm Bandits (Contextual)
    * Causality
  
---

# Expectation from this course

See [README.md](../README.md)