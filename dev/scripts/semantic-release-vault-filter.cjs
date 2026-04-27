const { execFileSync } = require("node:child_process");
const commitAnalyzer = require("@semantic-release/commit-analyzer");

function changedFiles(hash) {
  if (!hash) {
    return [];
  }
  const output = execFileSync("git", ["show", "--format=", "--name-only", hash], {
    encoding: "utf8",
  });
  return output
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function onlyVaultChanges(commit) {
  const files = changedFiles(commit.hash);
  return files.length > 0 && files.every((file) => file === "vault" || file.startsWith("vault/"));
}

async function analyzeCommits(pluginConfig, context) {
  const commits = context.commits.filter((commit) => !onlyVaultChanges(commit));
  return commitAnalyzer.analyzeCommits(pluginConfig, {
    ...context,
    commits,
  });
}

module.exports = { analyzeCommits };
