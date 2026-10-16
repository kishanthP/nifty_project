-- Runs once, the first time the Postgres volume is created.
-- A separate database for automated tests so they never touch real data.
CREATE DATABASE share_market_test;
