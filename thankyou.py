import csv
import db


with open('set_meta.csv', 'r') as f:
  db.RDS().insert(
    'scp_raw.new_set_meta',
    csv.DictReader(f),
    create_table=True,
  )
