
# Advanced consideration


---
## Implementation improvements

### Assignment process 

### Attribution logic 

---
# Enabling company changes
## Being part of the release process
## Helping team meet objectives
### Helping the ideation process 
## Reinforcing values
## Identify different motivations


---
# Optimizing Permutation computing

One of the issues with running permutation tests is that 10,000 permutaiton on large sample can represent a major computational cost. To remedy that there are commonly used optimization practice. 

## Computation Cells

One of the easiest is to assign each user to one of 100 cells, compute partial totals for each cell, and then shuffle cells to be randomly part of Treatment or Control. If computing statistics from 100 cells to two variants is cheaper than from all users to two variants, that can save a lot of effort.

A possible improvement of that approach is to use multiple mapping from users to cells, not always rely on the same bucketing.

Another improvement is to use two levels of cells; that one tends to make sense if you have more than 10,000,000 users.

### Days and weeks

Some metrics are harder to combine that way.
…

