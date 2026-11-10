# Deploying under a path

How to publish a vault at a path such as `https://example.com/notes/` on a domain whose other pages come from a separate Cloudflare Worker, and republish it on every push to the vault's Git repository.

## Layout

Two repositories, each deployed to its own Worker:

```text
root-site/                 vault/
  wrangler.toml              _site/
  public/                      mdblog.toml
    index.html                 mdblog-commit
    _redirects               notes.md ...
    robots.txt
```

The root site's Worker keeps its claim on the whole domain, as a Custom Domain or an `example.com/*` route. The vault's Worker claims the route `example.com/notes/*`. Cloudflare sends a request to the most specific matching route, and a route takes precedence over a Custom Domain on the same hostname ([Routes](https://developers.cloudflare.com/workers/configuration/routing/routes/)), so `/notes/` and everything below it reach the vault's Worker and every other path reaches the root site. Each repository deploys without touching the other.

The domain must already be a zone on your Cloudflare account, with a proxied DNS record for the hostname.

## The vault

In `_site/mdblog.toml`, set `base_url` to the site's full address, including the path, and add a `[worker]` table with the Worker's name and route ([Site folder](vault-format.md#site-folder) has the rules):

```toml
base_url = "https://example.com/notes/"
title = "Notes"
author = "Your Name"

[worker]
name = "example-notes"
routes = ["example.com/notes/*"]
```

The route's path must match `base_url`'s path. `mdblog deploy` checks the site at `base_url` after uploading it and fails if the route sends requests elsewhere. With `routes` set, the Worker has no `workers.dev` address, so the site exists only at `base_url`. A second hostname, such as `www.example.com`, serves the root site's pages under `/notes/` unless `routes` also lists `www.example.com/notes/*`.

Create `_site/mdblog-commit` holding one line: the full commit SHA of the mdblog version to build with. Cloudflare's build reads it, and mdblog ignores it.

## The root site

Add a redirect for the path without its trailing slash. A request for `/notes` does not match `example.com/notes/*`, so it reaches the root site. A root Worker that serves static assets takes it from a `_redirects` file in its assets directory ([Redirects](https://developers.cloudflare.com/workers/static-assets/redirects/)):

```text
/notes /notes/ 301
```

A root Worker with its own code needs the same redirect in that code.

Files that apply to the whole domain, such as `robots.txt`, `favicon.ico` and `.well-known/`, belong to the root site. Crawlers read only `/robots.txt`, so its rules govern `/notes/` as well, and a `robots.txt` in the vault's `_site/static/` has no effect.

To show recent posts on a root page, fetch `recent.json` from the vault's site. Its shape is a contract, stated in [`home.recent.json`](../src/mdblog/theme/layouts/home.recent.json). The page and the vault's site share an origin, so the request needs no CORS setup:

```html
<ul id="recent-posts"></ul>
<script>
  fetch("/notes/recent.json")
    .then((response) => response.json())
    .then(({ items }) => {
      const list = document.getElementById("recent-posts");
      for (const item of items) {
        const link = document.createElement("a");
        link.href = item.url;
        link.textContent = item.title;
        const date = document.createElement("time");
        date.dateTime = item.date;
        date.textContent = new Date(item.date).toLocaleDateString();
        const entry = document.createElement("li");
        entry.append(link, " ", date);
        if (item.summary) {
          const summary = document.createElement("p");
          summary.textContent = item.summary;
          entry.append(summary);
        }
        list.append(entry);
      }
    });
</script>
```

The script sets text with `textContent`, never `innerHTML`, because titles and summaries come from your notes. The list changes when the vault publishes, with no root-site deploy.

## First deploy

Deploy once from your computer, which creates the Worker and its route. In a checkout of mdblog, with its dependencies installed as the [README](../README.md#install) describes:

```sh
pixi run node_modules/.bin/wrangler login
pixi run mdblog deploy /path/to/vault
```

## Publishing on push

Cloudflare's Workers Builds runs `mdblog deploy` on every push to the vault repository's production branch ([Builds](https://developers.cloudflare.com/workers/ci-cd/builds/)). Whatever that branch holds then goes live, including an unfinished edit to a note that is already published. An Obsidian Git setup that pushes automatically publishes on each automatic push.

In the Cloudflare dashboard, open the vault's Worker, select **Settings**, then **Builds**, and connect the vault repository. Set:

- **Root directory:** the repository's root, the default.
- **Build command:** empty.
- **Deploy command:** the line below, with your mdblog repository's URL, the pixi version you use (`pixi --version`), and your time zone.

```sh
curl -fsSL https://pixi.sh/install.sh | PIXI_VERSION=vX.Y.Z PIXI_NO_PATH_UPDATE=1 sh && git clone https://github.com/OWNER/mdblog.git ~/mdblog && git -C ~/mdblog checkout "$(cat _site/mdblog-commit)" && ~/.pixi/bin/pixi run --manifest-path ~/mdblog/pixi.toml npm ci --prefix ~/mdblog && TZ=Area/City ~/.pixi/bin/pixi run --manifest-path ~/mdblog/pixi.toml mdblog deploy .
```

`TZ` sets the zone for each `date` written without an offset, which mdblog reads as the build machine's local time ([Properties](vault-format.md#properties)).

Under **Settings**, **Build**, **Branch control**, clear **Enable Preview Builds**. A push to another branch would otherwise run Cloudflare's default preview command, which needs a wrangler config the vault does not have.

Builds deploy with a token Cloudflare creates, which can edit Workers and their routes, so the vault repository holds no credentials.

## When a publish fails

When a note fails the build, `mdblog deploy` stops before uploading, and the live site does not change. The build's log in the dashboard lists each failing note.

When the site fails its checks after the upload, the new version is live. Roll back from the Worker's **Deployments** page or with `wrangler rollback` ([Rollbacks](https://developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks/)), then fix the vault and push again.

## Updating mdblog

Write the new commit SHA into `_site/mdblog-commit` and push. The push rebuilds the site with that version.
