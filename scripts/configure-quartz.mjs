import fs from "node:fs"
import path from "node:path"

const repoRoot = process.cwd()
const quartzDir = path.resolve(repoRoot, "quartz")
const packageJsonPath = path.join(quartzDir, "package.json")
const siteConfigPath = path.resolve(repoRoot, "config", "quartz-site.json")
const layoutConfigPath = path.resolve(repoRoot, "config", "quartz-layout.json")
const quartzConfigPath = path.join(quartzDir, "quartz.config.ts")
const quartzLayoutPath = path.join(quartzDir, "quartz.layout.ts")

if (!fs.existsSync(packageJsonPath)) {
  console.error(`Missing Quartz package at ${packageJsonPath}`)
  process.exit(1)
}

if (!fs.existsSync(siteConfigPath)) {
  console.error(`Missing site config at ${siteConfigPath}`)
  process.exit(1)
}

if (!fs.existsSync(layoutConfigPath)) {
  console.error(`Missing layout config at ${layoutConfigPath}`)
  process.exit(1)
}

const siteConfig = JSON.parse(fs.readFileSync(siteConfigPath, "utf8"))
const layoutConfig = JSON.parse(fs.readFileSync(layoutConfigPath, "utf8"))

const renderValue = (value) => JSON.stringify(value, null, 2)

const quartzConfig = `import { QuartzConfig } from "./quartz/cfg"
import * as Plugin from "./quartz/plugins"

const config: QuartzConfig = {
  configuration: {
    pageTitle: ${renderValue(siteConfig.pageTitle)},
    pageTitleSuffix: ${renderValue(siteConfig.pageTitleSuffix)},
    enableSPA: ${renderValue(siteConfig.enableSPA)},
    enablePopovers: ${renderValue(siteConfig.enablePopovers)},
    analytics: {
      provider: ${renderValue(siteConfig.analytics.provider)},
    },
    locale: ${renderValue(siteConfig.locale)},
    baseUrl: ${renderValue(siteConfig.baseUrl)},
    ignorePatterns: ${renderValue(siteConfig.ignorePatterns)},
    defaultDateType: ${renderValue(siteConfig.defaultDateType)},
    theme: {
      fontOrigin: ${renderValue(siteConfig.theme.fontOrigin)},
      cdnCaching: ${renderValue(siteConfig.theme.cdnCaching)},
      typography: {
        header: ${renderValue(siteConfig.theme.typography.header)},
        body: ${renderValue(siteConfig.theme.typography.body)},
        code: ${renderValue(siteConfig.theme.typography.code)},
      },
      colors: {
        lightMode: ${renderValue(siteConfig.theme.colors.lightMode)},
        darkMode: ${renderValue(siteConfig.theme.colors.darkMode)},
      },
    },
  },
  plugins: {
    transformers: [
      Plugin.FrontMatter(),
      Plugin.CreatedModifiedDate({
        priority: ${renderValue(siteConfig.createdModifiedDate.priority)},
      }),
      Plugin.SyntaxHighlighting({
        theme: {
          light: ${renderValue(siteConfig.syntaxHighlighting.theme.light)},
          dark: ${renderValue(siteConfig.syntaxHighlighting.theme.dark)},
        },
        keepBackground: ${renderValue(siteConfig.syntaxHighlighting.keepBackground)},
      }),
      Plugin.ObsidianFlavoredMarkdown({
        enableInHtmlEmbed: ${renderValue(siteConfig.obsidianFlavoredMarkdown.enableInHtmlEmbed)},
      }),
      Plugin.GitHubFlavoredMarkdown(),
      Plugin.TableOfContents(),
      Plugin.CrawlLinks({
        markdownLinkResolution: ${renderValue(siteConfig.crawlLinks.markdownLinkResolution)},
      }),
      Plugin.Description(),
      Plugin.Latex({
        renderEngine: ${renderValue(siteConfig.latex.renderEngine)},
      }),
    ],
    filters: [Plugin.RemoveDrafts()],
    emitters: [
      Plugin.AliasRedirects(),
      Plugin.ComponentResources(),
      Plugin.ContentPage(),
      Plugin.FolderPage(),
      Plugin.TagPage(),
      Plugin.ContentIndex({
        enableSiteMap: ${renderValue(siteConfig.contentIndex.enableSiteMap)},
        enableRSS: ${renderValue(siteConfig.contentIndex.enableRSS)},
      }),
      Plugin.Assets(),
      Plugin.Static(),
      Plugin.Favicon(),
      Plugin.NotFoundPage(),
      Plugin.CustomOgImages(),
    ],
  },
}

export default config
`

const footerLinks = Object.entries(layoutConfig.footer.links)
  .map(([label, url]) => `      ${JSON.stringify(label)}: ${JSON.stringify(url)},`)
  .join("\n")

const commentsComponent =
  layoutConfig.comments.enabled
    ? `Component.Comments({
      provider: "giscus",
      options: {
        repo: ${renderValue(layoutConfig.comments.giscus.repo)},
        repoId: ${renderValue(layoutConfig.comments.giscus.repoId)},
        category: ${renderValue(layoutConfig.comments.giscus.category)},
        categoryId: ${renderValue(layoutConfig.comments.giscus.categoryId)},
        mapping: ${renderValue(layoutConfig.comments.giscus.mapping)},
        strict: ${renderValue(layoutConfig.comments.giscus.strict)},
        reactionsEnabled: ${renderValue(layoutConfig.comments.giscus.reactionsEnabled)},
        inputPosition: ${renderValue(layoutConfig.comments.giscus.inputPosition)},
        lang: ${renderValue(layoutConfig.comments.giscus.lang)},
      },
    })`
    : ""

const afterBody = layoutConfig.comments.enabled ? `afterBody: [
    ${commentsComponent},
  ],` : "afterBody: [],"

const quartzLayout = `import { PageLayout, SharedLayout } from "./quartz/cfg"
import * as Component from "./quartz/components"

export const sharedPageComponents: SharedLayout = {
  head: Component.Head(),
  header: [],
  ${afterBody}
  footer: Component.Footer({
    links: {
${footerLinks}
    },
  }),
}

export const defaultContentPageLayout: PageLayout = {
  beforeBody: [
    Component.ConditionalRender({
      component: Component.Breadcrumbs(),
      condition: (page) => page.fileData.slug !== "index",
    }),
    Component.ArticleTitle(),
    Component.ContentMeta(),
    Component.TagList(),
  ],
  left: [
    Component.PageTitle(),
    Component.MobileOnly(Component.Spacer()),
    Component.Flex({
      components: [
        {
          Component: Component.Search(),
          grow: true,
        },
        { Component: Component.Darkmode() },
        { Component: Component.ReaderMode() },
      ],
    }),
    Component.Explorer(),
  ],
  right: [
    Component.Graph(),
    Component.DesktopOnly(Component.TableOfContents()),
    Component.Backlinks(),
  ],
}

export const defaultListPageLayout: PageLayout = {
  beforeBody: [Component.Breadcrumbs(), Component.ArticleTitle(), Component.ContentMeta()],
  left: [
    Component.PageTitle(),
    Component.MobileOnly(Component.Spacer()),
    Component.Flex({
      components: [
        {
          Component: Component.Search(),
          grow: true,
        },
        { Component: Component.Darkmode() },
      ],
    }),
    Component.Explorer(),
  ],
  right: [],
}
`

fs.writeFileSync(quartzConfigPath, quartzConfig)
fs.writeFileSync(quartzLayoutPath, quartzLayout)
console.log(`Wrote Quartz config from ${siteConfigPath} and ${layoutConfigPath}`)
