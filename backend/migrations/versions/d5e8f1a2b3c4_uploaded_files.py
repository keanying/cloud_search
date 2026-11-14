"""uploaded files (attachments parsed into markdown sources)

Revision ID: d5e8f1a2b3c4
Revises: b3c1d9a7e2f4
Create Date: 2026-11-14 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = 'd5e8f1a2b3c4'
down_revision: Union[str, Sequence[str], None] = 'b3c1d9a7e2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DT = sa.DateTime().with_variant(mysql.DATETIME(fsp=3), 'mysql')
BIGINT = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('src_opr_file_f'):
        return
    op.create_table(
        'src_opr_file_f',
        sa.Column('file_id', sa.String(64), nullable=False),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('conversation_id', sa.String(64), nullable=True),
        sa.Column('message_id', sa.String(64), nullable=True, comment='随哪条用户消息发送（发送前为空）'),
        sa.Column('display_name', sa.String(256), nullable=False),
        sa.Column('mime_name', sa.String(128), nullable=False),
        sa.Column('ext_name', sa.String(16), nullable=False),
        sa.Column('byte_qty', BIGINT, nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('storage_ref', sa.String(512), nullable=False),
        sa.Column('parse_status', sa.String(32), nullable=False, comment='queued/parsing/parsed/failed'),
        sa.Column('parser_name', sa.String(32), nullable=True, comment='builtin/mineru_api/mineru_cloud/...'),
        sa.Column('parse_detail', sa.String(256), nullable=True, comment='给用户看的解析说明'),
        sa.Column('parse_error', sa.Text(), nullable=True),
        sa.Column('page_qty', sa.Integer(), nullable=True),
        sa.Column('char_qty', sa.Integer(), nullable=True),
        sa.Column('table_qty', sa.Integer(), nullable=True),
        sa.Column('image_qty', sa.Integer(), nullable=True),
        sa.Column('markdown_ref', sa.String(512), nullable=True),
        sa.Column('outline', sa.JSON(), nullable=True, comment='标题大纲（≤40 条）'),
        sa.Column('preview_text', sa.Text(), nullable=True, comment='开头约 600 字，供需求编译了解文件内容'),
        sa.Column('worker_id', sa.String(64), nullable=True),
        sa.Column('lease_expire_time', DT, nullable=True),
        sa.Column('attempt_qty', sa.Integer(), nullable=False),
        sa.Column('file_status', sa.String(32), nullable=False, comment='active/deleted'),
        sa.Column('created_time', DT, nullable=False, comment='创建时间UTC'),
        sa.Column('updated_time', DT, nullable=False, comment='更新时间UTC'),
        sa.PrimaryKeyConstraint('file_id'),
        comment='用户在对话中上传的文件；解析为 Markdown 后作为来源参与问答与分析',
    )
    op.create_index('ix_file_conv', 'src_opr_file_f', ['conversation_id'])
    op.create_index('ix_file_parse', 'src_opr_file_f', ['parse_status', 'created_time'])


def downgrade() -> None:
    op.drop_index('ix_file_parse', table_name='src_opr_file_f')
    op.drop_index('ix_file_conv', table_name='src_opr_file_f')
    op.drop_table('src_opr_file_f')
