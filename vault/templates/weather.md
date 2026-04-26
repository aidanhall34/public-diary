<%*
const lat = -33.8167;
const lon = 151.0833;
const url =
  `https://api.open-meteo.com/v1/forecast` +
  `?latitude=${lat}` +
  `&longitude=${lon}` +
  `&daily=temperature_2m_max,temperature_2m_min,weather_code` +
  `&hourly=temperature_2m` +
  `&timezone=Australia%2FSydney` +
  `&forecast_days=1`;

const data = await tp.web.request(url);
const max = data.daily.temperature_2m_max[0];
const min = data.daily.temperature_2m_min[0];
const idx3pm = data.hourly.time.findIndex(t => t.endsWith("T15:00"));
const temp3pm = data.hourly.temperature_2m[idx3pm];
const code = data.daily.weather_code[0];

const isRain =
  (code >= 51 && code <= 67) ||
  (code >= 80 && code <= 82) ||
  (code >= 95 && code <= 99);

const condition = isRain ? "rainy" : "sunny";
const icon = isRain ? "🌧️" : "☀️";

tR += JSON.stringify({
  location: "Meadowbank",
  condition,
  icon,
  max,
  min,
  temp3pm,
  weatherCode: code
});
%>