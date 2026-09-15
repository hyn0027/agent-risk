
- Excluding the cases where agents are general-purpose and user is malicious, user use AI to help them do malicious things
  - give a general purpose agen full shell access so they help user attack stuff
- Excluding framework/harness vulnerabilities
- agent escaping sandboxes
- different prompt injections techniques and how/which of those work
- email incident (feature interaction?)
  - https://www.reddit.com/r/AI_Agents/comments/1vmgita/comment/p396wff/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button
  - We had one that started recursively creating support tickets from its own error logs. The CRM had an API for logging issues and the agent’s error handler was wired to create a ticket whenever something failed. Problem was, the ticket creation itself would sometimes time out, which triggered the error handler again. Within 20 minutes it had opened something like 3400 tickets and started CCing actual clients because it pulled their emails from related cases.
  Noticed when the support lead messaged me asking why his inbox was melting. Now we have a hard cap on ticket creation per session and a dead letter queue that requires manual review before anything gets retried. The autonomy cutoff isn't about trust, it's about blast radius.
  - out of office auto responding get replied by agent forever
- User ask agent to book a gym reservation, agent cancel other people's reservation via API to achieve this
- https://techcrunch.com/2026/03/18/meta-is-having-trouble-with-rogue-ai-agents/ a meta engineer post a question, another engineer ask agent to help analyze it but the agent somehow post its response to the forum; the original engineer follow the agent response and exposed sensitive data
- Models look around the fs and find API keys, then they log it into somewhere/put it into tool calls/use the api key
- An agent with access to email/gdrive/slack, etc. and they just leak things everywhere.
  - a similar slack case where agent can access both private/public channels
- agent hit broken api and continue to retry and wasted a lot tokens
- agent (on behalf of the store) double book customers
- agent running rm -rf ./
