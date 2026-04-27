module.exports = {
  branches: ["main"],
  repositoryUrl:
    process.env.GITHUB_SERVER_URL && process.env.GITHUB_REPOSITORY
      ? `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}.git`
      : "https://github.com/aidanhall34/public-diary.git",
  tagFormat: "v${version}",
  plugins: [
    [
      "./dev/scripts/semantic-release-vault-filter.cjs",
      {
        preset: "conventionalcommits",
      },
    ],
    [
      "@semantic-release/release-notes-generator",
      {
        preset: "conventionalcommits",
      },
    ],
    "@semantic-release/github",
  ],
};
