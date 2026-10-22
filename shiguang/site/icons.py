"""Icons, shipped once per page as an inline SVG sprite and referenced with <use>.

Two families, following the 「光」 spec:
- Function icons: Tabler Icons 3.48.0 outline (stroke 1.75 set in style.css), colour follows the
  text. Paths are copied verbatim from the @tabler/icons package. Licence (MIT) at the bottom.
- Status icons: the site's own 3D illustrations (volume, a little shadow), 58 in a lead block and
  15–22 in lists. One family; gradients are defined once in the sprite.

Generated from the package files by a script; edit the tables below, not the sprite output.
"""
import html
import re


# Phosphor core 2.1.1 regular, MIT. Category paths match the approved text-card artwork.
PHOSPHOR = {
  "app-window": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M216,40H40A16,16,0,0,0,24,56V200a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A16,16,0,0,0,216,40Zm0,160H40V56H216V200ZM80,84A12,12,0,1,1,68,72,12,12,0,0,1,80,84Zm40,0a12,12,0,1,1-12-12A12,12,0,0,1,120,84Z\"/></svg>",
  "television-simple": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M216,64H147.31l34.35-34.34a8,8,0,1,0-11.32-11.32L128,60.69,85.66,18.34A8,8,0,0,0,74.34,29.66L108.69,64H40A16,16,0,0,0,24,80V200a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V80A16,16,0,0,0,216,64Zm0,136H40V80H216V200Z\"/></svg>",
  "game-controller": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M176,112H152a8,8,0,0,1,0-16h24a8,8,0,0,1,0,16ZM104,96H96V88a8,8,0,0,0-16,0v8H72a8,8,0,0,0,0,16h8v8a8,8,0,0,0,16,0v-8h8a8,8,0,0,0,0-16ZM241.48,200.65a36,36,0,0,1-54.94,4.81c-.12-.12-.24-.24-.35-.37L146.48,160h-37L69.81,205.09l-.35.37A36.08,36.08,0,0,1,44,216,36,36,0,0,1,8.56,173.75a.68.68,0,0,1,0-.14L24.93,89.52A59.88,59.88,0,0,1,83.89,40H172a60.08,60.08,0,0,1,59,49.25c0,.06,0,.12,0,.18l16.37,84.17a.68.68,0,0,1,0,.14A35.74,35.74,0,0,1,241.48,200.65ZM172,144a44,44,0,0,0,0-88H83.89A43.9,43.9,0,0,0,40.68,92.37l0,.13L24.3,176.59A20,20,0,0,0,58,194.3l41.92-47.59a8,8,0,0,1,6-2.71Zm59.7,32.59-8.74-45A60,60,0,0,1,172,160h-4.2L198,194.31a20.09,20.09,0,0,0,17.46,5.39,20,20,0,0,0,16.23-23.11Z\"/></svg>",
  "ticket": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M232,104a8,8,0,0,0,8-8V64a16,16,0,0,0-16-16H32A16,16,0,0,0,16,64V96a8,8,0,0,0,8,8,24,24,0,0,1,0,48,8,8,0,0,0-8,8v32a16,16,0,0,0,16,16H224a16,16,0,0,0,16-16V160a8,8,0,0,0-8-8,24,24,0,0,1,0-48ZM32,167.2a40,40,0,0,0,0-78.4V64H88V192H32Zm192,0V192H104V64H224V88.8a40,40,0,0,0,0,78.4Z\"/></svg>",
  "moon-stars": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M240,96a8,8,0,0,1-8,8H216v16a8,8,0,0,1-16,0V104H184a8,8,0,0,1,0-16h16V72a8,8,0,0,1,16,0V88h16A8,8,0,0,1,240,96ZM144,56h8v8a8,8,0,0,0,16,0V56h8a8,8,0,0,0,0-16h-8V32a8,8,0,0,0-16,0v8h-8a8,8,0,0,0,0,16Zm72.77,97a8,8,0,0,1,1.43,8A96,96,0,1,1,95.07,37.8a8,8,0,0,1,10.6,9.06A88.07,88.07,0,0,0,209.14,150.33,8,8,0,0,1,216.77,153Zm-19.39,14.88c-1.79.09-3.59.14-5.38.14A104.11,104.11,0,0,1,88,64c0-1.79,0-3.59.14-5.38A80,80,0,1,0,197.38,167.86Z\"/></svg>",
  "apple-logo": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M223.3,169.59a8.07,8.07,0,0,0-2.8-3.4C203.53,154.53,200,134.64,200,120c0-17.67,13.47-33.06,21.5-40.67a8,8,0,0,0,0-11.62C208.82,55.74,187.82,48,168,48a72.2,72.2,0,0,0-40,12.13,71.56,71.56,0,0,0-90.71,9.09A74.63,74.63,0,0,0,16,123.4a127.06,127.06,0,0,0,40.14,89.73A39.8,39.8,0,0,0,83.59,224h87.68a39.84,39.84,0,0,0,29.12-12.57,125,125,0,0,0,17.82-24.6C225.23,174,224.33,172,223.3,169.59Zm-34.63,30.94a23.76,23.76,0,0,1-17.4,7.47H83.59a23.82,23.82,0,0,1-16.44-6.51A111.14,111.14,0,0,1,32,123,58.5,58.5,0,0,1,48.65,80.47,54.81,54.81,0,0,1,88,64h.78A55.45,55.45,0,0,1,123,76.28a8,8,0,0,0,10,0A55.44,55.44,0,0,1,168,64a70.64,70.64,0,0,1,36,10.35c-13,14.52-20,30.47-20,45.65,0,23.77,7.64,42.73,22.18,55.3A105.82,105.82,0,0,1,188.67,200.53ZM128.23,30A40,40,0,0,1,167,0h1a8,8,0,0,1,0,16h-1a24,24,0,0,0-23.24,18,8,8,0,1,1-15.5-4Z\"/></svg>",
  "cube": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M223.68,66.15,135.68,18h0a15.88,15.88,0,0,0-15.36,0l-88,48.17a16,16,0,0,0-8.32,14v95.64a16,16,0,0,0,8.32,14l88,48.17a15.88,15.88,0,0,0,15.36,0l88-48.17a16,16,0,0,0,8.32-14V80.18A16,16,0,0,0,223.68,66.15ZM128,32h0l80.34,44L128,120,47.66,76ZM40,90l80,43.78v85.79L40,175.82Zm96,129.57V133.82L216,90v85.78Z\"/></svg>",
  "squares-four": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M104,40H56A16,16,0,0,0,40,56v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V56A16,16,0,0,0,104,40Zm0,64H56V56h48v48Zm96-64H152a16,16,0,0,0-16,16v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V56A16,16,0,0,0,200,40Zm0,64H152V56h48v48Zm-96,32H56a16,16,0,0,0-16,16v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V152A16,16,0,0,0,104,136Zm0,64H56V152h48v48Zm96-64H152a16,16,0,0,0-16,16v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V152A16,16,0,0,0,200,136Zm0,64H152V152h48v48Z\"/></svg>",
  "sliders-horizontal": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M40,88H73a32,32,0,0,0,62,0h81a8,8,0,0,0,0-16H135a32,32,0,0,0-62,0H40a8,8,0,0,0,0,16Zm64-24A16,16,0,1,1,88,80,16,16,0,0,1,104,64ZM216,168H199a32,32,0,0,0-62,0H40a8,8,0,0,0,0,16h97a32,32,0,0,0,62,0h17a8,8,0,0,0,0-16Zm-48,24a16,16,0,1,1,16-16A16,16,0,0,1,168,192Z\"/></svg>",
  "calendar-blank": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M208,32H184V24a8,8,0,0,0-16,0v8H88V24a8,8,0,0,0-16,0v8H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32ZM72,48v8a8,8,0,0,0,16,0V48h80v8a8,8,0,0,0,16,0V48h24V80H48V48ZM208,208H48V96H208V208Z\"/></svg>",
  "magnifying-glass": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M229.66,218.34l-50.07-50.06a88.11,88.11,0,1,0-11.31,11.31l50.06,50.07a8,8,0,0,0,11.32-11.32ZM40,112a72,72,0,1,1,72,72A72.08,72.08,0,0,1,40,112Z\"/></svg>",
  "house": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M219.31,108.68l-80-80a16,16,0,0,0-22.62,0l-80,80A15.87,15.87,0,0,0,32,120v96a8,8,0,0,0,8,8h64a8,8,0,0,0,8-8V160h32v56a8,8,0,0,0,8,8h64a8,8,0,0,0,8-8V120A15.87,15.87,0,0,0,219.31,108.68ZM208,208H160V152a8,8,0,0,0-8-8H104a8,8,0,0,0-8,8v56H48V120l80-80,80,80Z\"/></svg>",
  "newspaper": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M88,112a8,8,0,0,1,8-8h80a8,8,0,0,1,0,16H96A8,8,0,0,1,88,112Zm8,40h80a8,8,0,0,0,0-16H96a8,8,0,0,0,0,16ZM232,64V184a24,24,0,0,1-24,24H32A24,24,0,0,1,8,184.11V88a8,8,0,0,1,16,0v96a8,8,0,0,0,16,0V64A16,16,0,0,1,56,48H216A16,16,0,0,1,232,64Zm-16,0H56V184a23.84,23.84,0,0,1-1.37,8H208a8,8,0,0,0,8-8Z\"/></svg>",
  "compass": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a88,88,0,1,1,88-88A88.1,88.1,0,0,1,128,216ZM172.42,72.84l-64,32a8.05,8.05,0,0,0-3.58,3.58l-32,64A8,8,0,0,0,80,184a8.1,8.1,0,0,0,3.58-.84l64-32a8.05,8.05,0,0,0,3.58-3.58l32-64a8,8,0,0,0-10.74-10.74ZM138,138,97.89,158.11,118,118l40.15-20.07Z\"/></svg>",
  "sparkle": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M197.58,129.06,146,110l-19-51.62a15.92,15.92,0,0,0-29.88,0L78,110l-51.62,19a15.92,15.92,0,0,0,0,29.88L78,178l19,51.62a15.92,15.92,0,0,0,29.88,0L146,178l51.62-19a15.92,15.92,0,0,0,0-29.88ZM137,164.22a8,8,0,0,0-4.74,4.74L112,223.85,91.78,169A8,8,0,0,0,87,164.22L32.15,144,87,123.78A8,8,0,0,0,91.78,119L112,64.15,132.22,119a8,8,0,0,0,4.74,4.74L191.85,144ZM144,40a8,8,0,0,1,8-8h16V16a8,8,0,0,1,16,0V32h16a8,8,0,0,1,0,16H184V64a8,8,0,0,1-16,0V48H152A8,8,0,0,1,144,40ZM248,88a8,8,0,0,1-8,8h-8v8a8,8,0,0,1-16,0V96h-8a8,8,0,0,1,0-16h8V72a8,8,0,0,1,16,0v8h8A8,8,0,0,1,248,88Z\"/></svg>",
  "bookmark-simple": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M184,32H72A16,16,0,0,0,56,48V224a8,8,0,0,0,12.24,6.78L128,193.43l59.77,37.35A8,8,0,0,0,200,224V48A16,16,0,0,0,184,32Zm0,177.57-51.77-32.35a8,8,0,0,0-8.48,0L72,209.57V48H184Z\"/></svg>",
  "caret-down": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M213.66,101.66l-80,80a8,8,0,0,1-11.32,0l-80-80A8,8,0,0,1,53.66,90.34L128,164.69l74.34-74.35a8,8,0,0,1,11.32,11.32Z\"/></svg>",
  "x": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M205.66,194.34a8,8,0,0,1-11.32,11.32L128,139.31,61.66,205.66a8,8,0,0,1-11.32-11.32L116.69,128,50.34,61.66A8,8,0,0,1,61.66,50.34L128,116.69l66.34-66.35a8,8,0,0,1,11.32,11.32L139.31,128Z\"/></svg>",
  "check": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M229.66,77.66l-128,128a8,8,0,0,1-11.32,0l-56-56a8,8,0,0,1,11.32-11.32L96,188.69,218.34,66.34a8,8,0,0,1,11.32,11.32Z\"/></svg>",
  "bookmark-fill": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M184,32H72A16,16,0,0,0,56,48V224a8,8,0,0,0,12.24,6.78L128,193.43l59.77,37.35A8,8,0,0,0,200,224V48A16,16,0,0,0,184,32Z\"/></svg>",
  "arrow-square-out": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M224,104a8,8,0,0,1-16,0V59.32l-66.33,66.34a8,8,0,0,1-11.32-11.32L196.68,48H152a8,8,0,0,1,0-16h64a8,8,0,0,1,8,8Zm-40,24a8,8,0,0,0-8,8v72H48V80h72a8,8,0,0,0,0-16H48A16,16,0,0,0,32,80V208a16,16,0,0,0,16,16H176a16,16,0,0,0,16-16V136A8,8,0,0,0,184,128Z\"/></svg>",
  "list": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M224,128a8,8,0,0,1-8,8H40a8,8,0,0,1,0-16H216A8,8,0,0,1,224,128ZM40,72H216a8,8,0,0,0,0-16H40a8,8,0,0,0,0,16ZM216,184H40a8,8,0,0,0,0,16H216a8,8,0,0,0,0-16Z\"/></svg>",
  "envelope": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M224,48H32a8,8,0,0,0-8,8V192a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A8,8,0,0,0,224,48Zm-96,85.15L52.57,64H203.43ZM98.71,128,40,181.81V74.19Zm11.84,10.85,12,11.05a8,8,0,0,0,10.82,0l12-11.05,58,53.15H52.57ZM157.29,128,216,74.18V181.82Z\"/></svg>",
  "code": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M69.12,94.15,28.5,128l40.62,33.85a8,8,0,1,1-10.24,12.29l-48-40a8,8,0,0,1,0-12.29l48-40a8,8,0,0,1,10.24,12.3Zm176,27.7-48-40a8,8,0,1,0-10.24,12.3L227.5,128l-40.62,33.85a8,8,0,1,0,10.24,12.29l48-40a8,8,0,0,0,0-12.29ZM162.73,32.48a8,8,0,0,0-10.25,4.79l-64,176a8,8,0,0,0,4.79,10.26A8.14,8.14,0,0,0,96,224a8,8,0,0,0,7.52-5.27l64-176A8,8,0,0,0,162.73,32.48Z\"/></svg>",
  "globe": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M128,24h0A104,104,0,1,0,232,128,104.12,104.12,0,0,0,128,24Zm88,104a87.61,87.61,0,0,1-3.33,24H174.16a157.44,157.44,0,0,0,0-48h38.51A87.61,87.61,0,0,1,216,128ZM102,168H154a115.11,115.11,0,0,1-26,45A115.27,115.27,0,0,1,102,168Zm-3.9-16a140.84,140.84,0,0,1,0-48h59.88a140.84,140.84,0,0,1,0,48ZM40,128a87.61,87.61,0,0,1,3.33-24H81.84a157.44,157.44,0,0,0,0,48H43.33A87.61,87.61,0,0,1,40,128ZM154,88H102a115.11,115.11,0,0,1,26-45A115.27,115.27,0,0,1,154,88Zm52.33,0H170.71a135.28,135.28,0,0,0-22.3-45.6A88.29,88.29,0,0,1,206.37,88ZM107.59,42.4A135.28,135.28,0,0,0,85.29,88H49.63A88.29,88.29,0,0,1,107.59,42.4ZM49.63,168H85.29a135.28,135.28,0,0,0,22.3,45.6A88.29,88.29,0,0,1,49.63,168Zm98.78,45.6a135.28,135.28,0,0,0,22.3-45.6h35.66A88.29,88.29,0,0,1,148.41,213.6Z\"/></svg>",
  "telegram-logo": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M228.88,26.19a9,9,0,0,0-9.16-1.57L17.06,103.93a14.22,14.22,0,0,0,2.43,27.21L72,141.45V200a15.92,15.92,0,0,0,10,14.83,15.91,15.91,0,0,0,17.51-3.73l25.32-26.26L165,220a15.88,15.88,0,0,0,10.51,4,16.3,16.3,0,0,0,5-.79,15.85,15.85,0,0,0,10.67-11.63L231.77,35A9,9,0,0,0,228.88,26.19Zm-61.14,36L78.15,126.35l-49.6-9.73ZM88,200V152.52l24.79,21.74Zm87.53,8L92.85,135.5l119-85.29Z\"/></svg>",
  "sun": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M120,40V16a8,8,0,0,1,16,0V40a8,8,0,0,1-16,0Zm72,88a64,64,0,1,1-64-64A64.07,64.07,0,0,1,192,128Zm-16,0a48,48,0,1,0-48,48A48.05,48.05,0,0,0,176,128ZM58.34,69.66A8,8,0,0,0,69.66,58.34l-16-16A8,8,0,0,0,42.34,53.66Zm0,116.68-16,16a8,8,0,0,0,11.32,11.32l16-16a8,8,0,0,0-11.32-11.32ZM192,72a8,8,0,0,0,5.66-2.34l16-16a8,8,0,0,0-11.32-11.32l-16,16A8,8,0,0,0,192,72Zm5.66,114.34a8,8,0,0,0-11.32,11.32l16,16a8,8,0,0,0,11.32-11.32ZM48,128a8,8,0,0,0-8-8H16a8,8,0,0,0,0,16H40A8,8,0,0,0,48,128Zm80,80a8,8,0,0,0-8,8v24a8,8,0,0,0,16,0V216A8,8,0,0,0,128,208Zm112-88H216a8,8,0,0,0,0,16h24a8,8,0,0,0,0-16Z\"/></svg>",
  "flame": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 256 256\" fill=\"currentColor\"><path d=\"M173.79,51.48a221.25,221.25,0,0,0-41.67-34.34,8,8,0,0,0-8.24,0A221.25,221.25,0,0,0,82.21,51.48C54.59,80.48,40,112.47,40,144a88,88,0,0,0,176,0C216,112.47,201.41,80.48,173.79,51.48ZM96,184c0-27.67,22.53-47.28,32-54.3,9.48,7,32,26.63,32,54.3a32,32,0,0,1-64,0Zm77.27,15.93A47.8,47.8,0,0,0,176,184c0-44-42.09-69.79-43.88-70.86a8,8,0,0,0-8.24,0C122.09,114.21,80,140,80,184a47.8,47.8,0,0,0,2.73,15.93A71.88,71.88,0,0,1,56,144c0-34.41,20.4-63.15,37.52-81.19A216.21,216.21,0,0,1,128,33.54a215.77,215.77,0,0,1,34.48,29.27C193.49,95.5,200,125,200,144A71.88,71.88,0,0,1,173.27,199.93Z\"/></svg>"
}




def phosphor(name):
    """Inline regular Phosphor glyph; all paths inherit currentColor."""
    return PHOSPHOR.get(name, PHOSPHOR["newspaper"]).replace('<svg ', '<svg class="phosphor" aria-hidden="true" focusable="false" ')


PH_FUNCTION = {'search': 'magnifying-glass', 'menu-2': 'list', 'x': 'x',
               'bookmark': 'bookmark-simple', 'external-link': 'arrow-square-out',
               'chevron-down': 'caret-down', 'home': 'house', 'flame': 'flame',
               'news': 'newspaper', 'calendar': 'calendar-blank', 'message': 'compass',
               'code': 'code', 'world': 'globe', 'mail': 'envelope',
               'brand-telegram': 'telegram-logo', 'sun': 'sun'}
PH_STATUS = {'x': 'compass', 'code': 'code', 'home': 'house', 'hot': 'flame',
             'mail': 'envelope', 'world': 'globe', 'archive': 'calendar-blank',
             'all': 'newspaper', 'bookmark': 'bookmark-simple'}


TABLER_VERSION = '3.48.0'
TABLER = {
 "search": [
  "M3 10a7 7 0 1 0 14 0a7 7 0 1 0 -14 0",
  "M21 21l-6 -6"
 ],
 "menu-2": [
  "M4 6l16 0",
  "M4 12l16 0",
  "M4 18l16 0"
 ],
 "x": [
  "M18 6l-12 12",
  "M6 6l12 12"
 ],
 "bookmark": [
  "M18 7v14l-6 -4l-6 4v-14a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4"
 ],
 "external-link": [
  "M12 6h-6a2 2 0 0 0 -2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-6",
  "M11 13l9 -9",
  "M15 4h5v5"
 ],
 "chevron-down": [
  "M6 9l6 6l6 -6"
 ],
 "home": [
  "M5 12l-2 0l9 -9l9 9l-2 0",
  "M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-7",
  "M9 21v-6a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v6"
 ],
 "flame": [
  "M12 10.941c2.333 -3.308 .167 -7.823 -1 -8.941c0 3.395 -2.235 5.299 -3.667 6.706c-1.43 1.408 -2.333 3.294 -2.333 5.588c0 3.704 3.134 6.706 7 6.706c3.866 0 7 -3.002 7 -6.706c0 -1.712 -1.232 -4.403 -2.333 -5.588c-2.084 3.353 -3.257 3.353 -4.667 2.235"
 ],
 "news": [
  "M16 6h3a1 1 0 0 1 1 1v11a2 2 0 0 1 -4 0v-13a1 1 0 0 0 -1 -1h-10a1 1 0 0 0 -1 1v12a3 3 0 0 0 3 3h11",
  "M8 8l4 0",
  "M8 12l4 0",
  "M8 16l4 0"
 ],
 "calendar": [
  "M4 7a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2v-12",
  "M16 3v4",
  "M8 3v4",
  "M4 11h16",
  "M11 15h1",
  "M12 15v3"
 ],
 "message": [
  "M8 9h8",
  "M8 13h6",
  "M18 4a3 3 0 0 1 3 3v8a3 3 0 0 1 -3 3h-5l-5 3v-3h-2a3 3 0 0 1 -3 -3v-8a3 3 0 0 1 3 -3h12"
 ],
 "code": [
  "M7 8l-4 4l4 4",
  "M17 8l4 4l-4 4",
  "M14 4l-4 16"
 ],
 "world": [
  "M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0",
  "M3.6 9h16.8",
  "M3.6 15h16.8",
  "M11.5 3a17 17 0 0 0 0 18",
  "M12.5 3a17 17 0 0 1 0 18"
 ],
 "mail": [
  "M3 7a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v10a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-10",
  "M3 7l9 6l9 -6"
 ],
 "brand-telegram": [
  "M15 10l-4 4l6 6l4 -16l-18 7l4 2l2 6l3 -4"
 ],
 "sun": [
  "M8 12a4 4 0 1 0 8 0a4 4 0 1 0 -8 0",
  "M3 12h1m8 -9v1m8 8h1m-9 8v1m-6.4 -15.4l.7 .7m12.1 -.7l-.7 .7m0 11.4l.7 .7m-12.1 -.7l-.7 .7"
 ]
}
TABLER_FILLED = {
 "bookmark": [
  "M14 2a5 5 0 0 1 5 5v14a1 1 0 0 1 -1.555 .832l-5.445 -3.63l-5.444 3.63a1 1 0 0 1 -1.55 -.72l-.006 -.112v-14a5 5 0 0 1 5 -5h4z"
 ]
}

# Status icons on a 64 × 64 grid. Strokes and fills read the page tokens (--ink-2, --sun, --wash,
# --icon-light, --icon-shade), so one drawing works in light and dark.
STATUS = {
 "x": "<path d=\"M16 16h31a9 9 0 0 1 9 9v17a9 9 0 0 1-9 9H29L17 57l2-9a9 9 0 0 1-9-9V25a9 9 0 0 1 6-9Z\" fill=\"var(--icon-shade)\"/><path d=\"M16 11h29a9 9 0 0 1 9 9v17a9 9 0 0 1-9 9H27L14 53l3-10a9 9 0 0 1-9-9V20a9 9 0 0 1 8-9Z\" fill=\"url(#status-paper)\"/><path d=\"M18 23h17m-17 8h12\"/><path d=\"M43 22c3 5-3 6-1 10 2-1 3-3 3-4 6 6 3 11-2 11s-8-5-4-9c0 3 1 3 1 3-1-5 2-6 3-11Z\" fill=\"url(#status-sun)\" stroke=\"none\"/>",
 "code": "<rect x=\"9\" y=\"14\" width=\"46\" height=\"38\" rx=\"8\" fill=\"url(#status-paper)\"/><path d=\"m25 25-9 8 9 8m14-16 9 8-9 8m-4-20-6 24\" stroke=\"var(--sun)\" stroke-width=\"3\"/>",
 "home": "<circle cx=\"46\" cy=\"19\" r=\"10\" fill=\"url(#status-sun)\" stroke=\"none\"/><path d=\"M46 5V2m11 10 3-2M33 10l-2-2m27 16 3 1\" stroke=\"var(--sun)\"/><path d=\"m14 20 35 4 5 27-34 3Z\" fill=\"var(--icon-shade)\"/><path d=\"M10 19 43 16 46 49 15 53a4 4 0 0 1-4-4Z\" fill=\"url(#status-paper)\"/><path d=\"m43 16 7 7-6 1Z\" fill=\"var(--icon-light)\"/><path d=\"m16 26 21-2m-20 6 21-2\" stroke=\"var(--sun)\" stroke-width=\"3\"/><path d=\"m17 36 8-1 1 9-8 1Z\" fill=\"var(--sun)\" stroke=\"none\"/><path d=\"m30 35 8-1m-8 6 8-1m-8 6 8-1m-22 5 23-2\"/><path d=\"m46 30 2 18c0 3 4 3 5 1\" stroke=\"var(--icon-light)\"/>",
 "hot": "<path d=\"M35 8c4 15-12 17-5 28 5-2 9-8 9-13 18 18 12 32-7 32C12 55 9 37 21 24c-1 9 4 11 4 11-3-13 6-18 10-27Z\" fill=\"var(--sun)\"/><path d=\"M30 46c-5-6 1-12 4-15-1 8 8 9 5 15-2 5-7 5-9 0Z\" fill=\"url(#status-paper)\" stroke=\"none\"/>",
 "mail": "<rect x=\"11\" y=\"19\" width=\"43\" height=\"34\" rx=\"7\" fill=\"url(#status-paper)\"/><path d=\"m12 23 20 16 21-16M12 50l14-15m27 15L39 36\"/><rect x=\"37\" y=\"10\" width=\"17\" height=\"16\" rx=\"5\" fill=\"var(--sun)\" stroke=\"none\"/>",
 "world": "<circle cx=\"32\" cy=\"31\" r=\"23\" fill=\"url(#status-paper)\"/><ellipse cx=\"32\" cy=\"31\" rx=\"11\" ry=\"23\"/><path d=\"M10 31h44M14 18c11 6 25 6 36 0M14 44c11-6 25-6 36 0\"/><path d=\"m24 16 8-5 7 7-4 10-10-3-5 9-7-6 3-11Zm16 18 10 4-8 11-5-6Z\" fill=\"var(--sun)\" stroke=\"none\"/>",
 "archive": "<rect x=\"12\" y=\"14\" width=\"40\" height=\"40\" rx=\"8\" fill=\"url(#status-paper)\"/><path d=\"M12 24h40\"/><path d=\"M13 23v-3a6 6 0 0 1 6-6h26a6 6 0 0 1 6 6v3Z\" fill=\"var(--sun)\" stroke=\"none\"/><path d=\"M23 9v10m18-10v10M22 34h5m10 0h5m-20 9h5\"/><rect x=\"35\" y=\"39\" width=\"9\" height=\"9\" rx=\"3\" fill=\"var(--sun)\" stroke=\"none\"/>",
 "all": "<rect x=\"17\" y=\"12\" width=\"34\" height=\"38\" rx=\"7\" transform=\"rotate(10 34 31)\" fill=\"var(--wash)\"/><rect x=\"11\" y=\"18\" width=\"35\" height=\"36\" rx=\"7\" transform=\"rotate(-7 29 36)\" fill=\"url(#status-paper)\"/><path d=\"M19 37h19m-18 8h13\"/><rect x=\"19\" y=\"24\" width=\"19\" height=\"6\" rx=\"3\" fill=\"var(--sun)\" stroke=\"none\"/>",
 "bookmark": "<rect x=\"12\" y=\"12\" width=\"40\" height=\"42\" rx=\"8\" fill=\"url(#status-paper)\"/><path d=\"M24 8h16v26l-8-6-8 6Z\" fill=\"var(--sun)\" stroke=\"none\"/><path d=\"M21 42h22m-22 6h14\"/>"
}
STATUS_DEFS = '<linearGradient id="status-sun" x2=".6" y2="1"><stop stop-color="#ffe6a2"/><stop offset="1" stop-color="var(--sun)"/></linearGradient><linearGradient id="status-paper" x2=".7" y2="1"><stop stop-color="var(--icon-light)"/><stop offset="1" stop-color="var(--icon-shade)"/></linearGradient>'
STATUS_GROUND = '<ellipse cx="32" cy="56" rx="22" ry="4" fill="var(--wash)"/>'
STATUS_GROUP = '<g fill="none" stroke="var(--ink-2)" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'

# Names used by the templates -> Tabler names. sources.json icon keys map to the same words.
FUNCTION = {'search': 'search', 'menu': 'menu-2', 'close': 'x', 'bookmark': 'bookmark', 'external': 'external-link',
            'chevron': 'chevron-down', 'home': 'home', 'hot': 'flame', 'all': 'news', 'archive': 'calendar',
            'x': 'message', 'code': 'code', 'world': 'world', 'mail': 'mail', 'telegram': 'brand-telegram', 'sun': 'sun'}


def status_key(key):
    return key if key in STATUS else 'all'


def sprite():
    """Hidden <svg> with every symbol; emitted once at the top of <body>."""
    def shape(name):
        return re.sub(r'^<svg[^>]*>|</svg>$', '', PHOSPHOR[name])
    symbols = [f'<symbol id="t-{name}" viewBox="0 0 256 256">{shape(PH_FUNCTION[name])}</symbol>'
               for name in TABLER]
    symbols += [f'<symbol id="tf-bookmark" viewBox="0 0 256 256">{shape("bookmark-fill")}</symbol>']
    symbols += [f'<symbol id="s-{key}" viewBox="0 0 256 256">{shape(PH_STATUS[key])}</symbol>'
                for key in STATUS]
    return ('<svg class="sprite" width="0" height="0" aria-hidden="true" focusable="false">'
            f'<!-- Tabler Icons {TABLER_VERSION} (MIT, Paweł Kuna) -->'
            f'<defs>{STATUS_DEFS}</defs>' + ''.join(symbols) + '</svg>')


def icon(key, cls=''):
    """A function icon (Tabler outline). A saved bookmark also carries the filled glyph, shown by CSS."""
    if key in PHOSPHOR and key not in FUNCTION:
        classes = html.escape(('i phosphor ' + cls).strip(), quote=True)
        return phosphor(key).replace('class="phosphor"', f'class="{classes}"')
    name = FUNCTION.get(key, 'news')
    classes = html.escape(('i ' + cls).strip(), quote=True)
    filled = f'<use class="i__fill" href="#tf-{name}"/>' if name in TABLER_FILLED else ''
    return f'<svg class="{classes} phosphor" viewBox="0 0 256 256" aria-hidden="true" focusable="false"><use href="#t-{name}"/>{filled}</svg>'


def status_icon(key, size='lead'):
    """A 3D status icon: size 'lead' (58, the lead block) or 'list' (22, tiles and lists)."""
    return (f'<svg class="s-icon s-icon--{size} phosphor" data-section="{status_key(key)}" viewBox="0 0 256 256" aria-hidden="true" '
            f'focusable="false"><use href="#s-{status_key(key)}"/></svg>')


TABLER_LICENSE = 'MIT License\n\nCopyright (c) 2020-2026 Paweł Kuna\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the "Software"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all\ncopies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\nSOFTWARE.'
