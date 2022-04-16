CREATE TABLE user_anki_config(
  userid BIGINT PRIMARY KEY,
  rollover INTEGER DEFAULT 4
);


CREATE TABLE user_anki_review_log(
  userid BIGINT NOT NULL REFERENCES user_anki_config (userid),
  reviewid BIGINT NOT NULL,
  time INTEGER,
  ease INTEGER,
  revtype INTEGER,
  PRIMARY KEY (userid, reviewid)
);
