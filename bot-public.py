from zipfile import ZipFile
from pykml import parser
import pathlib
from lxml import etree
import heapq
import geopy.distance
import pickle
from pykml.factory import nsmap
import os
from contextlib import suppress
from pykml.factory import KML_ElementMaker as KML
import json
import requests
from geopy.geocoders import ArcGIS
import time
import re


degrees_char = u'\N{DEGREE SIGN}'

geolocator = ArcGIS()

# Base directory for all files (script directory)
BASE_DIR = pathlib.Path(__file__).resolve().parent
# KML template/output file expected to live alongside this script
DOC_KML_PATH = BASE_DIR / 'doc.kml'
# Directory containing KMZ assets (doc.kml + any icon/image resources)
ASSETS_DIR = BASE_DIR


guild_id = 851583874768044052
channel_id = 1360751870381129868
start_messages = [("your teammate and decide what photos you are submitting", "rhoticity")]

loc_coords = 41.819915, -92.343759

def get_messages():
  headers = {
    "Authorization" : "REDACTED"
  }
  found_start_message = False
  messages = []
  params = {}
  last_message_id = None

  while not found_start_message:
    if last_message_id is not None:
      params['before'] = last_message_id
    r = requests.get(f"https://discord.com/api/v10/channels/{channel_id}/messages", headers=headers, params=params)
    print("status:", r.status_code)
    print("body:", r.text[:500])
    time.sleep(1)

    for m in json.loads(r.text):
      last_message_id = m['id']
      for (start_message, start_message_author) in start_messages:
        if m['author']['username'] == start_message_author and start_message.lower() in m['content'].lower():
          found_start_message = True
          break

      if found_start_message:
        break
      else:
        messages.append(m)

  messages.reverse()

  with open('messages.json', 'w', encoding='utf-8') as f:
    json.dump(messages, f, ensure_ascii=False, indent=2)

  return messages


with open(DOC_KML_PATH, 'rb') as kml_file:
  kml = kml_file.read()
  root = parser.fromstring(kml)

target_styleurl = "#icon-1502-FF5252"
gold_styleurl = "#icon-1899-FFEA00"
silver_styleurl = "#icon-1899-757575"
bronze_styleurl = "#icon-1899-795548"
top50_styleurl = "#icon-1899-0288D1"
bottom50_styleurl = "#icon-1899-3949AB"

ind_submission_styleurls = [
  "#icon-1535-000000",
  "#icon-1535-424242",
  "#icon-1535-757575",
  "#icon-1535-BDBDBD",
  "#icon-1535-A52714",
  "#icon-1535-795548",
  "#icon-1535-4E342E",
  "#icon-1535-E65100",
  "#icon-1535-F57C00",
  "#icon-1535-FF5252",
  "#icon-1535-FBC02D",
  "#icon-1535-F9A825",
  "#icon-1535-FFD600",
  "#icon-1535-FFEA00",
  "#icon-1535-AFB42B",
  "#icon-1535-817717",
  "#icon-1535-0F9D58",
  "#icon-1535-558B2F",
  "#icon-1535-7CB342",
  "#icon-1535-097138",
  "#icon-1535-01579B",
  "#icon-1535-006064",
  "#icon-1535-0097A7",
  "#icon-1535-0288D1",
  "#icon-1535-1A237E",
  "#icon-1535-3949AB",
  "#icon-1535-673AB7",
  "#icon-1535-9C27B0",
  "#icon-1535-C2185B",
  "#icon-1535-880E4F"
]


def get_coords(coord_obj):
  coords = str(coord_obj).strip().split(",")
  return coords[1], coords[0]

def clean_player_name(player):
  return str(player).strip(" *").strip()

def is_coord_char(c):
  if c in "NSEWnsew":
    return True

  return not c.isalpha()

def potential_part_of_coord_string(s):
  if len(s) > 0:
    if s[0].isalpha() and s[0].lower() not in "nswe":
      return False

    if s[0] in "\n(:":
      return False

  if len(s) > 1:
    if s[0].isalpha() and s[1].isalpha():
      return False

  for i, c in enumerate(s):
    if c.isdigit():
      return True

    if c in "NSEW":
      if i+1 == len(s) or not s[i+1].isalpha():
        return True

  return False

def is_start_of_coords(s, scan_i):
  scan_c = s[scan_i]
  if scan_c.isdigit() or scan_c == '-':
    maybe_start_of_coords = s[scan_i:scan_i + 6].split()[0]
    if '.' in maybe_start_of_coords or degrees_char in maybe_start_of_coords:
      return True

  return False


def get_potential_coord_string(s):
  scan_i = 0
  result = []
  while scan_i < len(s):
    if not is_start_of_coords(s, scan_i):
      scan_i += 1
      continue

    coord_string_end_i = scan_i
    while potential_part_of_coord_string(s[coord_string_end_i:coord_string_end_i+6]):
      coord_string_end_i += 1

    if coord_string_end_i == scan_i:
      scan_i += 1
      continue

    result.append(s[scan_i:coord_string_end_i])
    scan_i = coord_string_end_i

  return result


def parse_coords(message_string):
  print(f'message string: {message_string}')
  potential_coord_strings = get_potential_coord_string(message_string)
  print(f'potential_coord_strings: {potential_coord_strings}')
  results = []
  
  # Retry policy for geocoder fallbacks (avoid infinite hangs)
  MAX_GEOCODE_RETRIES = 5
  GEOCODE_RETRY_SLEEP_SECONDS = 1.5
  
  def _try_parse_numeric_latlon(s):
    """Parse 'lat, lon' from a string. Returns (lat, lon) or None."""
    m = re.search(r'(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)', s)
    if not m:
      return None
    a = float(m.group(1))
    b = float(m.group(2))
    # If it's clearly swapped (first looks like lon, second like lat), swap.
    if abs(a) > 90 and abs(b) <= 90:
      a, b = b, a
    # Validate ranges
    if not (-90 <= a <= 90 and -180 <= b <= 180):
      return None
    return (a, b)
  
  for raw in potential_coord_strings:
    # Fast path: numeric coordinate pair already present (don't geocode)
    numeric = _try_parse_numeric_latlon(raw)
    if numeric is not None:
      results.append(numeric)
      if len(results) == 2:
        return results
      continue
    
    # Skip obvious non-coordinate strings
    if '.' not in raw and degrees_char not in raw:
      continue
    
    # Clean to a geocoder-friendly string
    cleaned = raw.strip()
    cleaned = ''.join(filter(is_coord_char, cleaned))
    if not cleaned or len(cleaned) < 5:
      continue
    
    # Bounded geocode retry loop
    result_coords = None
    for attempt in range(1, MAX_GEOCODE_RETRIES + 1):
      try:
        result_coords = geolocator.geocode(cleaned)
        break
      except Exception as e:
        print(f"Failed parsing {cleaned} (attempt {attempt}/{MAX_GEOCODE_RETRIES}): {e}")
        time.sleep(GEOCODE_RETRY_SLEEP_SECONDS)
    
    if result_coords is None:
      print(f"Giving up on '{cleaned}' after {MAX_GEOCODE_RETRIES} attempts; moving on.")
      continue
    
    results.append((result_coords.latitude, result_coords.longitude))
    if len(results) == 2:
      return results
  
  return None

def has_image_embed(message):
  embeds = message['embeds']
  for embed in embeds:
    if embed['type'] == "image":
      return True

  return False

import math



def calculate_geographic_midpoint(coord1, coord2):
  lat1, lon1 = coord1
  lat2, lon2 = coord2

  lat1_rad = math.radians(lat1)
  lon1_rad = math.radians(lon1)
  lat2_rad = math.radians(lat2)
  lon2_rad = math.radians(lon2)

  # 2. Calculate the difference in longitude (delta_lon)
  dlon_rad = lon2_rad - lon1_rad

  # 3. Calculate the Cartesian (x, y, z) coordinates of the midpoint vector
  # This formula is derived from the mean of the two vectors from the Earth's center.
  # The X coordinate points towards (lat=0, lon=0) on the equator
  Bx = math.cos(lat2_rad) * math.cos(dlon_rad)
  By = math.cos(lat2_rad) * math.sin(dlon_rad)

  # 4. Calculate the midpoint latitude (mid_lat)
  mid_lat_rad = math.atan2(
      math.sin(lat1_rad) + math.sin(lat2_rad),
      math.sqrt((math.cos(lat1_rad) + Bx) ** 2 + By ** 2)
  )

  # 5. Calculate the midpoint longitude (mid_lon)
  mid_lon_rad = lon1_rad + math.atan2(By, math.cos(lat1_rad) + Bx)

  # 6. Convert the results back to degrees
  mid_lat = math.degrees(mid_lat_rad)
  mid_lon = math.degrees(mid_lon_rad)

  return (mid_lat, mid_lon)

player_name_map = {}
with suppress(FileNotFoundError):
  with open('player_map.json', 'r', encoding='utf-8') as f:
    player_name_map = json.load(f)


def get_player_name(player):
  global_name = player['global_name']
  player_id = player['id']
  mapped_name = ''
  if player_id in player_name_map:
    mapped_name = player_name_map[player_id]
  elif global_name is not None:
    mapped_name = global_name
  else:
    mapped_name = player['username']

  if player_id in player_name_map:
    if player_name_map[player_id] != mapped_name:
      raise Exception(f"Player {player_id} already has name set as {mapped_name}")
  else:
    if mapped_name in player_name_map.keys():
      raise Exception(f"Player name {mapped_name} already taken by player {player_id}")
    player_name_map[player_id] = mapped_name

  return mapped_name

dist_map = {}
geodesic_dist_map = {}
midpoints = []

messages = []

messages = get_messages()

player_name = None
player_id = None
new_player_id = None
coords = None
pic_link = None
added_placemark = False
no_placemarks = []
other_player_name = ''
ind_submissions_map = {}
for message in messages:
  if player_id is None:
    player_id = message['author']['id']
    player_name = message['author']['username']
  new_player_id = message['author']['id']
  if new_player_id != player_id:
    if not added_placemark:
      no_placemarks.append(player_name)
      print(f"---------------------------------\nNo placemark added for {player_name}\n---------------------------------")
    player_id = new_player_id
    player_name = message['author']['username']
    coords = None
    pic_link = None
    added_placemark = False
    other_player_name = ''
  message_content = message['content']
  message_snapshots = message.get('message_snapshots', [])
  stickers = message.get('sticker_items', [])
  mentions = message.get('mentions', [])
  if not message_content and len(message_snapshots) > 0:
    message_content = message_snapshots[0]['message']['content']

  if not other_player_name:
    for mention in mentions:
      if mention['id'] == player_id:
        continue
      other_player_name = get_player_name(mention)

  if coords is None:
    coords = parse_coords(message_content)
  if len(message['attachments']) > 0 or has_image_embed(message) or len(message_snapshots) > 0 or len(stickers) > 0:
    pic_link = f"https://discord.com/channels/{guild_id}/{channel_id}/{message['id']}"
  for mention in mentions:
    if mention['id'] == player_id:
        continue
    other_player_name = get_player_name(mention)
  if coords is not None and pic_link is not None:
    mapped_name = get_player_name(message['author'])

    combined_name = ''
    if mapped_name < other_player_name:
      combined_name = f'{mapped_name},{other_player_name}'
    else:
      combined_name = f'{other_player_name},{mapped_name}'

    for pm in midpoints:
      pm_name = str(pm.name)
      if clean_player_name(combined_name).lower() == clean_player_name(pm_name).lower():
        combined_name = pm_name
    added_placemark = True
    midpoint = calculate_geographic_midpoint(coords[0], coords[1])

    ind_submissions_map[combined_name] = (
      KML.Placemark(
          KML.name(mapped_name),
          KML.description(pic_link),
          KML.styleUrl(),
          KML.Point(
            KML.coordinates(f"{coords[0][1]},{coords[0][0]},0"))
          ),
      KML.Placemark(
          KML.name(other_player_name),
          KML.description(pic_link),
          KML.styleUrl(),
          KML.Point(
            KML.coordinates(f"{coords[1][1]},{coords[1][0]},0"))
          )
      )

    midpoints.append(
      KML.Placemark(
        KML.name(combined_name),
        KML.description(pic_link),
        KML.styleUrl(),
        KML.Point(
          KML.coordinates(f"{midpoint[1]},{midpoint[0]},0"))
        ))


    time.sleep(1)

# Handle the last message
if not added_placemark:
  no_placemarks.append(player_name)
  print(f"---------------------------------\nNo placemark added for {player_name}\n---------------------------------")

print(f'\n\nNo placemarks: {no_placemarks}\n')

for pm in midpoints:
  pm_coords = get_coords(pm.Point.coordinates)
  dist = geopy.distance.great_circle(pm_coords, loc_coords).km
  geodesic_dist = geopy.distance.geodesic(pm_coords, loc_coords).km
  name = pm.name
  dist_map[name] = dist
  geodesic_dist_map[name] = geodesic_dist

sorted_dist_map = {k: v for k, v in sorted(dist_map.items(), key=lambda item: item[1])}

rank_map = {}
medal_rank_map = {}
rank = 1
medal_rank = 0
tie_group_dist = -1
tie_group_geodesic_dist = -1
medal_tie_dist = 0.05
for player in sorted_dist_map:
  dist = sorted_dist_map[player]
  geodesic_dist = geodesic_dist_map[player]
  if dist - tie_group_dist > medal_tie_dist and geodesic_dist - tie_group_geodesic_dist > medal_tie_dist:
    medal_rank += 1
    tie_group_dist = dist
    tie_group_geodesic_dist = geodesic_dist

  print(f"{player}: {dist}")
  rank_map[player] = rank
  medal_rank_map[player] = medal_rank
  rank += 1

player_count = len(rank_map)
print("Total submissions:", player_count)

output_len = player_count + 1
sorted_players = [None for i in range(output_len)]
sorted_players[0] = KML.Placemark(
    KML.name(f"{loc_coords[0]}, {loc_coords[1]}"),
    KML.styleUrl(target_styleurl),
    KML.Point(
      KML.coordinates(f"{loc_coords[1]},{loc_coords[0]},0"))
    )
ind_submissions = [None for i in range(output_len * 2)]

players_set = set()
for pm in midpoints:
  player = pm.name
  rank = rank_map[player]
  medal_rank = medal_rank_map[player]

  (player1, player2) = ind_submissions_map[player]
  players_set.add(player1.name)
  players_set.add(player2.name)
  ind_styleurl = ind_submission_styleurls[(rank - 1) % len(ind_submission_styleurls)]
  player1.styleUrl = ind_styleurl
  player2.styleUrl = ind_styleurl
  ind_submissions[rank * 2 - 2] = player1
  ind_submissions[rank * 2 - 1] = player2

  sorted_players[rank] = pm
  if medal_rank == 1:
    pm.styleUrl = gold_styleurl
  elif medal_rank == 2:
    pm.styleUrl = silver_styleurl
  elif medal_rank == 3:
    pm.styleUrl = bronze_styleurl
  elif rank <= player_count / 2:
    pm.styleUrl = top50_styleurl
  else:
    pm.styleUrl = bottom50_styleurl

root.Document.Folder[0].Placemark = sorted_players
root.Document.Folder[0].name = 'Submissions'

root.Document.Folder[1].Placemark = ind_submissions
root.Document.Folder[1].name = 'Individual Submissions'

with open(DOC_KML_PATH,'wb') as f:
  f.write(etree.tostring(root, pretty_print=True))

directory = ASSETS_DIR
with ZipFile("Output.kmz", mode="w") as archive:
  # Include doc.kml plus common KMZ asset types (images, overlays, etc.) from ASSETS_DIR.
  asset_suffixes = {'.kml', '.png', '.jpg', '.jpeg', '.gif', '.svg'}
  for file_path in ASSETS_DIR.iterdir():
    if not file_path.is_file():
      continue
    if file_path.name == 'Output.kmz':
      continue
    if file_path.suffix.lower() in asset_suffixes:
      archive.write(file_path, arcname=file_path.name)
with open('player_map.json', 'w', encoding='utf-8') as f:
  json.dump(player_name_map, f, ensure_ascii=False, indent=2)

submission_reminder_string = "Submission reminders:"
# with suppress(FileNotFoundError):
#   with open('pinglist.json', 'r', encoding='utf-8') as f:
#     pinglist = json.load(f)

#     for p in pinglist:
#       if p not in player_name_map or player_name_map[p].strip().lower() not in players_set:
#         submission_reminder_string += " " + f"<@{p}>"

submission_reminder_string = ""
with suppress(FileNotFoundError):
  with open("player_list.txt", "r") as f:
    tpg_players = f.read()
    tpg_players_list = tpg_players.splitlines()

    print("Players missing from player list:")
    for p in players_set:
      if p not in tpg_players_list:
        print(p)

    print("\nPlayers missing submissions:")

    for p in tpg_players_list:
      if p not in players_set:
        print(p)

        player_id = next((key for key, val in player_name_map.items() if val == p), None)
        submission_reminder_string += " " + f"<@{player_id}>"

print(submission_reminder_string)
print("If you would like to be added to the submission reminders list reacc to this message")