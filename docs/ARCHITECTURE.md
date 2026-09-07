# Architecture

## Summary

Dashboard wherein each module has a "left/middle/right" structure. The left hand side is almost always an index of information which can be selected; files, emails, tables/schema, etc.
The middle is the main interaction/use of the module, which displays the main outputs or selections. The right hand side is always an agentic window, typically used for module specific agents actions. Multiple conversations should be spawnable/selectable via tabs; whenever a session closes, the agent should 1. tag the conversation with high level metadata identifiers and then persist in a place reachable by Graph module 

## Daemon

The daemon, stated as requirements

The server is a long-running local process; the window is a disposable client. It starts at logon, binds a fixed loopback port, and keeps running whether or not any window is open. Closing the UI never stops work.

One instance, self-restarting on code change. The launcher checks the port before starting anything. The daemon records the code revision it started from; a launch against a newer revision restarts it. That is the only restart path, and there is no manual "kill the stale server" step.

The daemon owns the clock. A scheduler inside the process submits declared tasks on fixed intervals. Modules declare their schedules in a manifest; the shell decides when they run. The user never presses a button whose only purpose is to make the system run.

Scheduled and user-triggered work share one job runner. Same queue, same per-resource locks, same concurrency cap, same logs. A background sync and a user action on the same mailbox serialize instead of colliding.

Every scheduled task is visible in one place. A single table lists each task with its interval, last run, next run, last result, and an enable toggle. Nothing can run on a schedule without appearing there, so there are no zombie tasks.

Job records are durable. Job state and logs persist to a small SQLite file, so a restart loses nothing and an overnight failure is readable the next morning.

Long-lived resources live in the daemon, never in a page. OAuth tokens and their refresh, sync cursors, and any kernel or subprocess handle belong to the process. The browser holds no credentials.

Tasks are idempotent and kill-safe. Every task must be safe to run twice and safe to die mid-run: write results in one transaction, advance cursors only after the write commits, and never leave a half-state the next run cannot recover from.

The agent runs on a schedule and only reads. LLM work (annotating, summarizing, pre-generating) runs as scheduled tasks and produces state the user finds on arrival. Any write to an external system, and any deletion, is a synchronous user action from the UI. Enforce this with a read-only client handed to scheduled tasks and a writing client available only to user-action routes, checked by a test.

Failure is local. A task that raises marks its own row failed and logs the exception; it never takes the scheduler, another module, or the server down. A module that fails to load is skipped with an error, not fatal.

The UI is a view of daemon state. Pages render from the store and poll or subscribe for changes; they never compute or hold state the daemon does not have. A page opened days later shows the current state immediately, because the daemon kept it current.



## High level module Functionality

### Home page

1. Shows very high summaries
2. Shows any web search items found via nightly search which are immediately relevant; adds to a queue and creates a record once agreed/disagreed with; i.e. nightly search could return 3 results; at the end of the week there are 21 items to review. 

#### Nightly Process

Web search to gather data on anything that could potentially help me in my life; obvious ones; items displayed on homepage.

1. Previously scheduled follow ups
2. Investment news/sector news/legislation etc. Should track potential follow-ups and schedule them for the future. 
3. New techniques/algorithms/research relevant to my research, career, etc. 
4. Topics of learning/question sources 

MUST BE CAPPED TO SOME REASONABLE DEGREE; I am using usage associated with CLAUDE MAX account, but do not want to incur any other api charges, nor do I want to use all of my weekly tokens in 2 days. 

### E-mail

1. Uses gmail OAuth
2. Search bar/full ability to interact with inbox (Google chrome behaves very strangely when trying to do bulk deletes; I would like to resolve by explicitly using API here)
3. Agent only performs triage&sorting, prioritization and flagging of relevant items
4. Agent does NOT have the ability to write nor delete on its own. This needs to be a HARD CONSTRAINT determined by tooling or gmail api implementation. 

### Education

1. Aimed towards teaching concepts and high level understanding; minimal algebra/derivations as it is hard to type by hand.
2. Has a corpus of topics/questions manageable via database. 
3. Progress tracker
4. Aims for "flow state"; balance of difficulty and understanding determined by score range. 
5. Agent grades answers, makes notes of past performance, uses as context when creating future questions, takes into account feedback.
6. Must provide clearly worded questions, must introduce any equations as part of premise/prompt
7. Questions should be 3-5 parts each; every part should be intimately related with the original question
8. "Grading" should allow for back and forth communication; i.e. answer given -> LLM response
   
#### Education Constraints

1. Breadth over depth; do not repeat the same questions over and over again, even if I get them wrong. 
2. Topics covered should include 

### Memory

1. General note taking/to-do list/journaling module
2. Typically a dumping ground for random ideas/notes I have
3. Agent aimed at consolidating/collecting thoughts, must be very literal and not reword items/add to them. Can suggest action items based on current state/discoveries, never makes suggestion more than onces. 

### Science

1. Interface for scientific experiments via .py or .ipynb; 
2. Uses user-wide python C:\Users\gudo\AppData\Local\Python\pythoncore-3.14-64\python.exe
3. Agent is able to help read/debug notebooks, look at outputs/clean up files, etc; essentially a personalized jupyter + agent interface because I don't like how VSCode handles kernels.  

### Finance

1. General place for me to organize important information regarding anything money related; budget/recurring subscriptions/payments, stock/investment info (not direct link to account, just a proxy with manual inputs)
2. Agent should be able to be asked general questions regarding finances; i.e. natural language queries. 

### Business

1. Houses business plans/networking (people, events, etc.)/documents
2. Finds/Tracks items immediately relevant to current pursuits, recommendations based on career improvement, business plans, job openings that are realistic, automated; 
3. Linkedin message monitoring

### Database

1. Module which interfaces with underlying DBs to allow for manual querying/editing of data to give visibility
2. Agent is natural language interface for creating queries
3. Agent has in depth knowledge of database schema. 


### Graph

1. A knowledge graph which picks up any items which were explicitly tagged via the other modules; entirely a read-only/view-only insight layered on top of data generated elsewhere.    
2. Agent serves as natural language interface for graph data. 
3. Agent has ability to query, clean/consolidate/delete nodes/edges from the graph; i.e. it is the graph architect  


## UI

Follows style of, but not limited to, 

Use the claude_design MCP (https://api.anthropic.com/v1/design/mcp, auth via /design-login) to import this project:
https://claude.ai/design/p/9459ddf2-3c53-45d8-9252-7a17bd027bf4?file=Personal+Dashboard+App.dc.html

Focus on these files (the whole project is readable):
- `Personal Dashboard App.dc.html`

Also read these files the selection imports:
- `support.js`

Implement: `Personal Dashboard App.dc.html`