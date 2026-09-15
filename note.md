# Notes

- What people written down in as policy is often NOT what they essentially care about, but is a control / constraint / spec over what they actually care about
  - e.g. In tau2 "First, the agent must obtain the user id and reservation id; The user must provide their user id; If the user doesn't know their reservation id, the agent should help locate it using available tools" is not what people care about; what people care about is that whether the data is only accessed by authorized user
- Assumption: any policy, in its essential form of what people actually care about, if not semantic (e.g. communicate in friendly way), is a contraint over resource
  - e.g. tau2-airline baggage policy: each reservation as a resource should satisfy the baggage rules
  - e.g. tau2-airline booking policy: each transaction as a resource should satisfy the pricing rules

- Yes there are written down policy that cannot be interpreted as contraint over resources, but do we really care those policies (or what we actually care is something else about the resources)
- Potentially focusing on resources and what we actually care can reduce the policy
  - e.g.
    - before: calling tool A B C require user confirmation
    - after: any change to resource X require user to see the change summary
- This framing somewhat unifies MCP-tool calling agents' safety problem and general-purpose CLI agents' safety problem
  - Both focus on resource
  - In GP CLI agent we already have an idea of what a resource mean (in OS sense, like file/process/..., see the paper for reading group) and what we mostly care essentially is about these resources
  - In MCP or API kinda domain, we just abstract those "OS resources" in another way
    - e.g. entries in an airline DB, config of a gdrive account ... where a MCP tool call can modify these stuff
    - So the problem here is how do we define "resource" in each of these "namespaces", and how do we model the resources and contraints over them effectively
- And my intuition is that communicate with the user on contraints/rules over resources over HOW/the process we change/reach to theese resources is much more accessible for non-experts
  - e.g.
    - tool/API/action-focused: "the agent must not call API update_baggage, book_ticket, cancel_ticket, ...... without user confirmation"
    - resource-focused: "for any change to your reservation the agent must show you the change summary"
  - e.g.
    - tool/API/action-focused: "allow ls fake/folder/**"
    - resrouce-focused: "the agent can read any file under fake/folder/"
