# Views page

A **View** is a user-curated, named collection of runs (a saved selection),
independent of which Experiment a run belongs to. The Views page lists the user's
views; clicking one filters the Runs page to just that view's runs. This document
describes how the feature is wired and the bugs that were fixed to make it work.

## Data model

`View` (`models.py`) has a `type` (`VIEW_TYPE_CHOICES`):

| type | name shown | origin | user-deletable |
|------|-----------|--------|----------------|
| `unsubmitted` | "Unsubmitted" | auto-created (`create_default_views`) | no |
| `default` | "Selected" | auto-created (`create_default_views`) | no |
| `user-defined` | (user's name) | created via "Save selection" | yes |
| `tutorial` | "Tutorials" | synthetic (frontend, id `-1`) | no |

Runs ↔ views is a many-to-many (`run.views`). `unsubmitted`/`default` are
**internal system views**: `Unsubmitted` is repopulated on each list with the
user's runs that have no execution (`populate_unsubmitted_runs`); `Selected`
backs the transient "Save selection" flow. **Only `user-defined` views are meant
to appear in the Views page and the left-nav.**

## Request flow

- **List** — `GET /epolyscat_django_app/api/views/?page=&page_size=`
  (`ViewsViewSet.list`). Ensures the system views exist (`create_default_views`),
  repopulates `Unsubmitted`, and returns the owner's non-deleted views via
  `ViewSerializer`. Each view embeds its `runs` (full `RunSerializer` data),
  `run_count`, and `active_run_count`.
- **Detail** — `GET /api/views/<id>/` returns one view with its runs (used to
  filter the Runs page).
- **Create** — `POST /api/views/` `{name, runIds}` → a `user-defined` view; the
  listed runs are attached.
- **Delete** — `DELETE /api/views/<id>/` → `perform_destroy` soft-deletes
  (`deleted = True`); only `user-defined` views may be deleted.

## Frontend pieces

- `components/Pages/Views.vue` — the page (table of the user's views).
- `components/blocks/AppLeftNav.vue` — the left-nav Views section (top 4 by
  recency).
- `service/epolyscat-service.js` → `ViewService` — REST calls + `encodeObj`
  (maps the API shape to the UI shape).
- `store/modules/view-storage.store.js` — Vuex module: `viewMap` (id→view),
  `viewListMap`/`viewListPaginationMap` (per-query result + pagination).
- `components/Pages/Runs.vue` — reads `?viewId=` and filters runs to the view.

`encodeObj` maps `id → {id, viewId}`, `active_run_count → activeRunCount`,
`run_count → runCount`, and formats `created`/`updated` with
`toLocaleString("en-US", {dateStyle:"long", timeStyle:"medium"})`
("June 14, 2023 at 12:27:40").

## The Views table

Columns: checkbox · **Name** (link to `/runs/?viewId=<id>`) · **Last edited** ·
**Active runs** · **Actions** (delete). Empty state: *"No views created yet — …"*.
The page filters the store to `type === "user-defined"`, so system views never
appear and the empty state shows when the user has made none.

## Filtering Runs by a view

The view name/count link to `/runs/?viewId=<id>` (a **query** param). `Runs.vue`
reads `this.$route.query.viewId`; when set, `refreshData` dispatches
`view/fetchView` and stores the view in `this.view`, and the `runs()` computed
returns `this.view.runs` instead of all runs. A `watch` on `viewId`/`experimentId`
re-fetches and clears the cached view when the filter changes (the component is
reused across `/runs`, `?viewId=`, and `?experimentId=`).

## Bugs fixed (2026-06-22)

All of these were preventing the page from working; each is a STAR note.

1. **Render data missing (`encodeObj`).** *Situation:* `encodeObj` emitted `id`
   (not `viewId`) with `activeRunCount` commented out, so the table's
   `view.viewId`/`view.activeRunCount` were `undefined` (blank count, broken
   delete/links) and dates were raw ISO. *Action:* emit `viewId` and
   `activeRunCount` and format the dates. *Result:* rows render with name,
   formatted date, count, and working delete.

2. **Store state uninitialised.** *Situation:* `viewListMap`/
   `viewListPaginationMap` were commented out of the module `state`, so
   `getViewsPagination` dereferenced `undefined[queryString]` and threw on first
   render. *Action:* initialise both to `{}`. *Result:* the getter returns
   `null` pre-fetch and the page renders.

3. **Pagination null-deref.** *Situation:* the template binds
   `viewsPagination.total` during the initial render, but the getter returns
   `null` until the first fetch. *Action:* the `viewsPagination` computed falls
   back to `{total: 0}` (mirrors the Experiments page guard). *Result:* no crash
   before data loads.

4. **Create 500 (`ViewSerializer.create`).** *Situation:* `owner` was passed
   explicitly while `serializer.save(owner=…)` already injected it →
   `got multiple values for keyword argument 'owner'`, so every create failed.
   *Action:* drop the duplicate `owner` and pop any client-sent `type`. *Result:*
   creating a view returns 200.

5. **Deleted views lingered (`get_queryset`).** *Situation:* `perform_destroy`
   only soft-deletes, but `get_queryset` didn't exclude `deleted=True`, so
   deleted views kept appearing. *Action:* filter `deleted=False`. Also
   `Views.vue` commits `view/REMOVE_VIEW` on delete (the getter reads the whole
   accumulating map). *Result:* deleted views disappear immediately and stay
   gone.

6. **System views shown / not deletable.** *Situation:* "Unsubmitted"/"Selected"
   appeared in both the Views page and the left-nav, with delete buttons that
   500 (only `user-defined` is deletable), and they suppressed the empty state.
   *Action:* both consumers filter to `type === "user-defined"`. *Result:* only
   user views show; the empty state appears when there are none.

7. **Run filtering by view broken (`Runs.vue`).** *Situation:* `viewId()` read
   `$route.params.viewId`, but the id arrives as a query param, so it was always
   `null` → no view fetched → all runs shown. There was also no watcher, so
   switching views didn't re-fetch. *Action:* read `$route.query.viewId` and add
   a `watch` that re-fetches and resets the cached view. *Result:*
   `/runs/?viewId=<id>` shows that view's runs; switching/leaving updates.

## Build / verify

Frontend changes require a rebuild:
`cd epolyscat_django_app && NODE_OPTIONS=--openssl-legacy-provider yarn build`
(then hard-reload, Ctrl+Shift+R — bundles cache hard). Backend verified live:
create → 200, delete → 204 then absent from the list, `/api/views/<id>/` returns
the view's runs.

## Notes / follow-ups
- `getViews` returns the whole `viewMap` rather than the current query's page;
  the per-consumer `user-defined` filter + `REMOVE_VIEW`-on-delete cover the
  current flows, but a getter scoped to `viewListMap[queryString]` would be
  cleaner (a commented-out version exists in the store).
- `View` has no `description` field; the page's old Description column was
  removed.
