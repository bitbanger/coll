create schema if not exists scp_bronze;

begin;
drop view if exists scp_bronze.sets;
create view scp_bronze.sets as
select
	value as id,
	(case when pg_input_is_valid(split_part(label, ' ', 1), 'integer')
		then split_part(label, ' ', 1)::int
		else null
	end) as year,
	(case when pg_input_is_valid(split_part(label, ' ', 1), 'integer')
		then substring(label from position(' ' in label) + 1)
		else label
	end) as name,
	etl_category as category,

	(to_timestamp(etl_time::bigint) at time zone 'America/New_York') at time zone 'America/New_York' as etl_time

from scp_raw.sets
where value is not null
;
commit;

begin;
drop view if exists scp_bronze.cards;
create view scp_bronze.cards as
select
	c.id,
	c.etl_set_id as set_id,

	s.name as set_name,
	s.year as set_year,
	s.category as category,

	c.iscard::bool as is_card,
	replace(replace(c.price1, ',', ''), '$', '')::numeric(19,2) as price_raw,
	replace(replace(c.price3, ',', ''), '$', '')::numeric(19,2) as price_psa9,
	replace(replace(c.price2, ',', ''), '$', '')::numeric(19,2) as price_psa10,

	split_part(split_part(c.productname, ' #', 1), ' [', 1) as name,
	split_part(c.productname, ' #', 2) as number,
	(case when c.productname like '%[%]%' then
		split_part(split_part(c.productname, '[', 2), ']', 1)
	else null end) as parallel,

	c.imageuri as image_uri,

	(to_timestamp(c.etl_time::bigint) at time zone 'America/New_York') at time zone 'America/New_York' as etl_time

from
	scp_raw.cards c
	join scp_bronze.sets s
		on c.etl_set_id=s.id
;
commit;