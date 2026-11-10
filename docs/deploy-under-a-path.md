# Deploying under a path

How to publish a vault at a path such as `https://example.com/notes/` on a domain whose other pages come from a separate Cloudflare Worker, and republish it on every push to the vault's Git repository.

## Layout

Two repositories, each deployed to its own Worker:

```text
root-site/                 vault/
  wrangler.toml              _site/
  public/                      mdblog.toml
    index.html                 deploy.sh
    _redirects               notes.md ...
    robots.txt
```

The root site's Worker keeps its claim on the whole domain, as a Custom Domain or an `example.com/*` route. The vault's Worker claims the route `example.com/notes/*`. Cloudflare sends a request to the most specific matching route, and a route takes precedence over a Custom Domain on the same hostname ([Routes](https://developers.cloudflare.com/workers/configuration/routing/routes/)), so `/notes/` and everything below it reach the vault's Worker and every other path reaches the root site. Each repository deploys without touching the other.

The domain must already be a zone on your Cloudflare account, with a proxied DNS record for the hostname.

## The vault

In `_site/mdblog.toml`, set `base_url` to the site's full address, including the path, set `timezone`, and add a `[worker]` table with the Worker's name and route ([Site folder](vault-format.md#site-folder) has the rules):

```toml
base_url = "https://example.com/notes/"
title = "Notes"
author = "Your Name"
timezone = "America/New_York"

[worker]
name = "example-notes"
routes = ["example.com/notes/*"]
```

`timezone` makes a `date` written without an offset mean the same time on your computer and on Cloudflare's build machines, which run in another zone. The route's path must match `base_url`'s path: `mdblog deploy` checks the site at `base_url` after uploading it and fails if the route sends requests elsewhere. With `routes` set, the Worker has no `workers.dev` address, so the site exists only at `base_url`.

Copy [`templates/deploy.sh`](../templates/deploy.sh) to `_site/deploy.sh`, and replace its commit placeholder with the full SHA of the mdblog commit to build with, such as the output of `git rev-parse HEAD` in your mdblog checkout. Cloudflare's build runs it: it clones mdblog at that commit and runs mdblog's [`tools/workers-build`](../tools/workers-build), which installs mdblog's tools and runs `mdblog deploy` on the vault. If you build from a fork of mdblog, change the script's repository URL too.

## The root site

Add a redirect for the path without its trailing slash. A request for `/notes` does not match `example.com/notes/*`, so it reaches the root site. A root Worker that serves static assets takes it from a `_redirects` file in its assets directory ([Redirects](https://developers.cloudflare.com/workers/static-assets/redirects/)):

```text
/notes /notes/ 301
```

A root Worker with its own code needs the same redirect in that code.

Files that apply to the whole domain, such as `robots.txt`, `favicon.ico` and `.well-known/`, belong to the root site. Crawlers read only `/robots.txt`, so its rules govern `/notes/` as well, and a `robots.txt` in the vault's `_site/static/` has no effect.

### Recent posts on a root page

A root page can list the vault's newest posts by fetching `recent.json` from the vault's site. Its shape is a contract, stated in [`home.recent.json`](../src/mdblog/theme/layouts/home.recent.json). The page and the vault's site share an origin, so the request needs no CORS setup:

```html
<section class="recent-posts">
  <h2><a href="/notes/">Notes</a></h2>
  <ul class="recent-posts-list"></ul>
</section>
<script>
  fetch("/notes/recent.json")
    .then((response) => {
      if (!response.ok) throw new Error(`recent.json: HTTP ${response.status}`);
      return response.json();
    })
    .then(({ items }) => {
      const list = document.querySelector(".recent-posts-list");
      for (const item of items) {
        const link = document.createElement("a");
        link.className = "recent-post-title";
        link.href = item.url;
        link.textContent = item.title;
        const date = document.createElement("time");
        date.className = "recent-post-date";
        date.dateTime = item.date;
        date.textContent = new Date(item.date).toLocaleDateString(undefined, {
          dateStyle: "medium",
        });
        const entry = document.createElement("li");
        entry.className = "recent-post";
        entry.append(link, " ", date);
        if (item.summary) {
          const summary = document.createElement("p");
          summary.className = "recent-post-summary";
          summary.textContent = item.summary;
          entry.append(summary);
        }
        list.append(entry);
      }
    })
    .catch((error) => console.warn(error));
</script>
```

The script sets text with `textContent`, never `innerHTML`, because titles and summaries come from your notes. When the fetch fails, the list stays empty and the heading's link to `/notes/` remains. The list changes when the vault publishes, with no root-site deploy.

To style the entries:

- Style the class names in the root site's own stylesheet. The vault's stylesheet never loads on the root page, so the list takes on the root site's look.
- Change how dates read with the `toLocaleDateString` options, such as `{ month: "long", day: "numeric" }`. `dateStyle: "medium"` follows the reader's locale.
- Keep summaries to a line or two, for example with `line-clamp`, so a long lede does not crowd the page.
- Keep a plain link to the notes, as the heading above does, so the section is useful when scripts are off.

```css
.recent-posts-list {
  list-style: none;
  padding: 0;
}
.recent-post {
  margin-bottom: 1em;
}
.recent-post-date {
  opacity: 0.7;
  font-size: 0.9em;
}
.recent-post-summary {
  margin: 0.25em 0 0;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
}
```

## First deploy

Deploy once from your computer, which creates the Worker and its route. In a checkout of mdblog, with its dependencies installed as the [README](../README.md#install) describes:

```sh
pixi run node_modules/.bin/wrangler login
pixi run mdblog deploy /path/to/vault
```

## Publishing on push

Cloudflare's Workers Builds runs `_site/deploy.sh` on every push to the vault repository's production branch ([Builds](https://developers.cloudflare.com/workers/ci-cd/builds/)). Whatever that branch holds then goes live, including an unfinished edit to a note that is already published. An Obsidian Git setup that pushes automatically publishes on each automatic push.

In the Cloudflare dashboard, open the vault's Worker, select **Settings**, then **Build**, and connect the vault repository. Set:

- **Root directory:** the repository's root, the default.
- **Build command:** empty.
- **Deploy command:** `sh _site/deploy.sh`

Under **Branch control** in the same settings, clear **Enable Preview Builds**. A push to another branch would otherwise run Cloudflare's default preview command, which needs a wrangler config the vault does not have.

Builds deploy with a token Cloudflare creates, which can edit Workers and their routes, so the vault repository holds no credentials.

## When a publish fails

When a note fails the build, `mdblog deploy` stops before uploading, and the live site does not change. The build's log in the dashboard lists each failing note.

When the site fails its checks after the upload, the new version is live. Roll back from the Worker's **Deployments** page or with `wrangler rollback` ([Rollbacks](https://developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks/)), then fix the vault and push again.

## Updating mdblog

Write the new commit SHA into `_site/deploy.sh` and push. The push rebuilds the site with that version. Compare your copy with the current [`templates/deploy.sh`](../templates/deploy.sh) when you do, in case the template has changed.
