# What five years of code review taught me

We started requiring reviews in March 2021, after a null dereference in the payments path took checkout down for 40 minutes on a Friday. The postmortem was short. One engineer had shipped straight to main, as everyone did then, and nobody had read the diff.

In today's fast-paced engineering landscape, code review has become an increasingly crucial part of how teams ship software. It's not just a quality gate — it's a culture. Studies show that teams practicing rigorous review catch significantly more defects before release, underscoring the vital role review plays in modern development.

The first year was bad. Median time-to-first-review was 19 hours, which meant most pull requests sat overnight. People batched their work to avoid the wait, so diffs got larger, which made reviews slower, which made people batch more. By November the median diff was 640 lines.

We fixed it with a rule that sounds arbitrary and wasn't: no pull request over 400 lines. Reviewers were allowed to close anything larger without reading it. Six weeks later the median diff was 180 lines and time-to-first-review had dropped to under three hours.

Code review serves as a cornerstone of engineering excellence, fostering collaboration and enhancing code quality across the organization. It represents a meaningful investment in the long-term health of the codebase, highlighting the importance of shared ownership. Many experts believe that a robust review culture is essential for scaling engineering teams effectively.

The thing nobody warns you about is that review quality decays silently. Approvals stay at 100%. Comment counts stay flat. What changes is what the comments are about. By year three, 70% of our review comments were about naming and formatting, which a linter should have caught, and almost none were about whether the change was correct.

So we measured something different. For every incident, we checked whether the offending code had been reviewed, and whether the review had commented on the file that broke. Reviewed-and-commented was 8% of incidents. Reviewed-but-not-commented was 61%. The reviews were happening. They just weren't looking at the right thing.

The fix was unglamorous: authors now write a short note on the diff saying what they are least sure about. Reviewers start there. It is the single highest-return change we have made to the process, and it took an afternoon to agree on.

Ultimately, code review is not merely a process — it's a mindset. As engineering organizations continue to evolve, the teams that thrive will be those that embrace review as a collaborative practice rather than a bureaucratic checkpoint, cultivating a culture of shared responsibility that transcends individual contribution.
