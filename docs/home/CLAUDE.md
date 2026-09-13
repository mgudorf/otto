# Home

1. Shows very high summaries
2. Shows any web search items found via nightly search which are immediately relevant; adds to a queue and creates a record once agreed/disagreed with; i.e. nightly search could return 3 results; at the end of the week there are 21 items to review. 

## Built

`GET /api/home/numbers` (one number per module with a `numbers` hook) and `GET /api/home/left`, which reads every module that is not switched off, page or not, in rail order, and puts a `Review` group per module with a `queue` hook first, every waiting row and no cut (an empty queue yields no group), then each module's `today` rows, five per module with a `+N` link into the module (an empty day still yields the group, shown as `nothing today`). Groups and numbers carry `page`; a header, `+N` or number navigates only when it is true. Three modules queue: Search's open findings, Business's open leads and Memory's open suggestions, each waiting under `Review` however old it is and decided from Home's inspector. Groups are keyed `label:module`, so one module can yield both. MIDDLE blank state is the number grid; selecting a row opens the owning module's item inspector and posts its verbs as `{id}` to that module's action route (an `href` opens a tab, `confirm` prompts, an action marked `removes` clears the selection because its row is gone from the list). The Home agent has no tools; its Current state block carries the same numbers, today rows and `Review: N waiting` lines.

## Nightly Process

Web search to gather data on anything that could potentially help me in my life; obvious ones; items displayed on homepage.

1. Previously scheduled follow ups
2. Investment news/sector news/legislation etc. Should track potential follow-ups and schedule them for the future. 
3. New techniques/algorithms/research relevant to my research, career, etc. 
4. Topics of learning/question sources 

MUST BE CAPPED TO SOME REASONABLE DEGREE; I am using usage associated with CLAUDE MAX account, but do not want to incur any other api charges, nor do I want to use all of my weekly tokens in 2 days. 

### Built

The Search module runs the nightly web search over the owner's topics in the three kinds `money`, `work` and `learn`; `business.scout` searches for leads against the owner's plans. The `[nightly]` budget caps every scheduled LLM run.
