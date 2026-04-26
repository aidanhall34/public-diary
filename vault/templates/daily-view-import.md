  <%*

const p = `daily-notes/${tp.date.now("YYYY/MM")}/${tp.date.now("YYYY-MM-DD")}.md`;
const f = app.vault.getAbstractFileByPath(p);
if (!f) throw new Error(`Missing: ${p}`);
const note = await app.vault.read(f);
const weatherJson = (await tp.file.include("[[weather]]")).trim();
const weatherData = JSON.parse(weatherJson);
const weatherBlock =
  `## Weather — ${weatherData.location}\n\n` +
  `${weatherData.condition} ${weatherData.icon}\n\n` +
  `- Max: ${weatherData.max}°C\n` +
  `- Min: ${weatherData.min}°C\n` +
  `- 3pm: ${weatherData.temp3pm}°C`;
const m = note.match(/^---\n[\s\S]*?\n---\n?/);
const content = m
  ? `${m[0].trimEnd()}\n\n${weatherBlock}\n\n---\n\n${note.slice(m[0].length).trimStart()}`
  : `${weatherBlock}\n\n---\n\n${note.trimStart()}`;
await app.vault.modify(tp.config.target_file, content);
%>
