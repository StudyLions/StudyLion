from typing import TypeAlias, Union

from core.data import RankType

from data import RowModel, Registry, Table, RegisterEnum
from data.columns import Integer, String, Timestamp, Bool


class RankData(Registry):
    RankType = RegisterEnum(RankType, name='RankType')

    class XPRank(RowModel):
        """
        Schema
        ------
        CREATE TABLE xp_ranks(
          rankid SERIAL PRIMARY KEY,
          roleid BIGINT NOT NULL,
          guildid BIGINT NOT NULL REFERENCES guild_config ON DELETE CASCADE,
          required INTEGER NOT NULL,
          reward INTEGER NOT NULL,
          message TEXT
        );
        CREATE UNIQUE INDEX xp_ranks_roleid ON xp_ranks (roleid);
        CREATE INDEX xp_ranks_guild_required ON xp_ranks (guildid, required);
        """
        _tablename_ = 'xp_ranks'

        rankid = Integer(primary=True)
        roleid = Integer()
        guildid = Integer()
        required = Integer()
        reward = Integer()
        message = String()

    class VoiceRank(RowModel):
        """
        Schema
        ------
        CREATE TABLE voice_ranks(
          rankid SERIAL PRIMARY KEY,
          roleid BIGINT NOT NULL,
          guildid BIGINT NOT NULL REFERENCES guild_config ON DELETE CASCADE,
          required INTEGER NOT NULL,
          reward INTEGER NOT NULL,
          message TEXT
        );
        CREATE UNIQUE INDEX voice_ranks_roleid ON voice_ranks (roleid);
        CREATE INDEX voice_ranks_guild_required ON voice_ranks (guildid, required);
        """
        _tablename_ = 'voice_ranks'

        rankid = Integer(primary=True)
        roleid = Integer()
        guildid = Integer()
        required = Integer()
        reward = Integer()
        message = String()

    class MsgRank(RowModel):
        """
        Schema
        ------
        CREATE TABLE msg_ranks(
          rankid SERIAL PRIMARY KEY,
          roleid BIGINT NOT NULL,
          guildid BIGINT NOT NULL REFERENCES guild_config ON DELETE CASCADE,
          required INTEGER NOT NULL,
          reward INTEGER NOT NULL,
          message TEXT
        );
        CREATE UNIQUE INDEX msg_ranks_roleid ON msg_ranks (roleid);
        CREATE INDEX msg_ranks_guild_required ON msg_ranks (guildid, required);
        """
        _tablename_ = 'msg_ranks'

        rankid = Integer(primary=True)
        roleid = Integer()
        guildid = Integer()
        required = Integer()
        reward = Integer()
        message = String()

    class MemberRank(RowModel):
        """
        Schema
        ------
        CREATE TABLE member_ranks(
          guildid BIGINT NOT NULL,
          userid BIGINT NOT NULL,
          current_xp_rankid INTEGER REFERENCES xp_ranks ON DELETE SET NULL,
          current_voice_rankid INTEGER REFERENCES voice_ranks ON DELETE SET NULL,
          current_msg_rankid INTEGER REFERENCES msg_ranks ON DELETE SET NULL,
          last_roleid BIGINT,
          PRIMARY KEY (guildid, userid),
          FOREIGN KEY (guildid, userid) REFERENCES members (guildid, userid)
        );
        """
        _tablename_ = 'member_ranks'

        guildid = Integer(primary=True)
        userid = Integer(primary=True)
        current_xp_rankid = Integer()
        current_voice_rankid = Integer()
        current_msg_rankid = Integer()
        last_roleid = Integer()


AnyRankData: TypeAlias = Union[RankData.XPRank, RankData.VoiceRank, RankData.MsgRank]
