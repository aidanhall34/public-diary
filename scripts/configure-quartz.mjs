import fs from "node:fs"
import path from "node:path"

const repoRoot = process.cwd()
const quartzDir = path.resolve(repoRoot, "quartz")
const packageJsonPath = path.join(quartzDir, "package.json")
const siteConfigPath = path.resolve(repoRoot, "config", "quartz-site.json")
const quartzConfigPath = path.join(quartzDir, "quartz.config.ts")

if (!fs.existsSync(packageJsonPath)) {
  console.error(`Missing Quartz package at ${packageJsonPath}`)
  process.exit(1)
}

if (!fs.existsSync(siteConfigPath)) {
  console.error(`Missing site config at ${siteConfigPath}`)
  process.exit(1)
}

const siteConfig = JSON.parse(fs.readFileSync(siteConfigPath, "utf8"))

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

fs.writeFileSync(quartzConfigPath, quartzConfig)
console.log(`Wrote Quartz config from ${siteConfigPath}`)
