---
creation date: <% tp.file.creation_date() %>
modification date: <% tp.file.last_modified_date("dddd Do MMMM YYYY HH:mm:ss") %>
weather: '  <% JSON.parse(await tp.file.include("[[weather]]")).condition %>'
---
# Notes for {{date:DD-MM-YYYY}}
## todo


## today I will


## today I did


## Tags


#daily #notes #<% JSON.parse(await tp.file.include("[[weather]]")).condition %>