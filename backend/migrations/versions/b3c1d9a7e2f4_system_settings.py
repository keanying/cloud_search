"""system settings overridden from admin console

Revision ID: b3c1d9a7e2f4
Revises: 57f4cb6bf707
Create Date: 2026-11-14 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = 'b3c1d9a7e2f4'
down_revision: Union[str, Sequence[str], None] = '57f4cb6bf707'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DT = sa.DateTime().with_variant(mysql.DATETIME(fsp=3), 'mysql')


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('src_opr_system_setting_f'):
        return  # 由早期版本的 create_all 建过
    op.create_table(
        'src_opr_system_setting_f',
        sa.Column('setting_key', sa.String(length=64), nullable=False, comment='参数键，如 search_engines'),
        sa.Column('setting_value', sa.JSON(), nullable=True, comment='参数值（JSON）'),
        sa.Column('updated_by_id', sa.String(length=64), nullable=True, comment='最后修改人'),
        sa.Column('created_time', DT, nullable=False, comment='创建时间UTC'),
        sa.Column('updated_time', DT, nullable=False, comment='更新时间UTC'),
        sa.PrimaryKeyConstraint('setting_key'),
        comment='管理后台修改的运行参数（覆盖 config.yaml 中的同名项，无需重启）',
    )


def downgrade() -> None:
    op.drop_table('src_opr_system_setting_f')
