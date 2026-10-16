"""parties

Phase 2b item 1 (FSD v0.1 KYC-01 … KYC-04, KYC-11). One party per person or
organisation, with identifiers (unique across all branches), contacts,
addresses, bank accounts, roles, links between parties (directors, next of kin,
guarantors with the amount committed …) and signing mandates. Parties are never
deleted. KYC verification is a change request (party.verify).

Revision ID: b8c9d0e1f2a3
Revises: a6f7b8c9d0e1
Create Date: 2026-10-16 15:30:40.730265

"""
import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8c9d0e1f2a3'
down_revision = 'a6f7b8c9d0e1'
branch_labels = None
depends_on = None

SEED_DATE = '2026-01-01'
PERMISSIONS = [
    ('party.view', 'View clients and their KYC details', True, ('user', 'admin', 'super_admin')),
    ('party.create', 'Create clients', False, ('user', 'admin', 'super_admin')),
    ('party.edit', 'Edit clients and propose controlled changes (maker)', False, ('user', 'admin', 'super_admin')),
    ('party.change.approve', 'Approve changes to client identity, bank and payout details (checker)', False,
     ('admin', 'super_admin')),
    ('kyc.verify', "Approve a client's KYC verification (checker)", False, ('admin', 'super_admin')),
]
POLICIES = [
    ('party.verify', [{'permission': 'kyc.verify', 'count': 1}], "A second person verifies a client's KYC."),
]
# key, value, evidence (frozen copy of the registry defaults)
SEEDS = [
    ('kyc.required_fields.person', sorted(['name', 'id_document', 'kra_pin', 'date_of_birth', 'mobile',
                                           'physical_address', 'next_of_kin']), '07 Q-C1'),
    ('kyc.required_fields.organisation', sorted(['legal_name', 'registration_no', 'kra_pin', 'registration_date',
                                                 'director_with_id', 'phone', 'physical_address']), '07 Q-C1'),
]
GUARD = """
CREATE FUNCTION parties_refuse_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Clients are never deleted; merge duplicates through a change request.'
        USING ERRCODE = 'insufficient_privilege';
END
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_parties_no_delete BEFORE DELETE ON parties
    FOR EACH ROW EXECUTE FUNCTION parties_refuse_delete();
"""


def upgrade():
    op.execute("CREATE SEQUENCE party_no_seq START 1")
    op.create_table('parties',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('party_no', sa.String(length=12), nullable=False),
    sa.Column('party_type', sa.String(length=12), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=False),
    sa.Column('home_branch_id', sa.Integer(), server_default='1', nullable=False),
    sa.Column('classification', sa.String(length=40), nullable=True),
    sa.Column('risk_rating', sa.String(length=10), nullable=True),
    sa.Column('is_pep', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('kyc_status', sa.String(length=15), server_default='incomplete', nullable=False),
    sa.Column('status', sa.String(length=12), server_default='active', nullable=False),
    sa.Column('merged_into_party_id', sa.Integer(), nullable=True),
    sa.Column('relationship_officer_user_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verified_by', sa.String(length=120), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by', sa.String(length=120), nullable=False),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(kyc_status = 'verified') = (verified_at IS NOT NULL)", name='ck_parties_verified'),
    sa.CheckConstraint("(status = 'merged') = (merged_into_party_id IS NOT NULL)", name='ck_parties_merged'),
    sa.CheckConstraint("kyc_status IN ('incomplete', 'pending_review', 'verified')", name='ck_parties_kyc_status'),
    sa.CheckConstraint("party_type IN ('person', 'organisation')", name='ck_parties_type'),
    sa.CheckConstraint("risk_rating IS NULL OR risk_rating IN ('low', 'medium', 'high')", name='ck_parties_risk'),
    sa.CheckConstraint("status IN ('active', 'blacklisted', 'merged')", name='ck_parties_status'),
    sa.ForeignKeyConstraint(['home_branch_id'], ['branches.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['merged_into_party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['relationship_officer_user_id'], ['user.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('party_no')
    )
    with op.batch_alter_table('parties', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_parties_home_branch_id'), ['home_branch_id'], unique=False)

    op.create_table('party_addresses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('line1', sa.String(length=200), nullable=False),
    sa.Column('line2', sa.String(length=200), nullable=True),
    sa.Column('town', sa.String(length=100), nullable=True),
    sa.Column('county', sa.String(length=100), nullable=True),
    sa.Column('country', sa.String(length=2), server_default='KE', nullable=False),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('home', 'business', 'postal', 'registered')", name='ck_party_addresses_kind'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('party_addresses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_party_addresses_party_id'), ['party_id'], unique=False)

    op.create_table('party_bank_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('bank_name', sa.String(length=100), nullable=True),
    sa.Column('branch_name', sa.String(length=100), nullable=True),
    sa.Column('account_no', sa.String(length=100), nullable=False),
    sa.Column('account_name', sa.String(length=150), nullable=True),
    sa.Column('is_default_payout', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='active', nullable=False),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('bank', 'mpesa')", name='ck_party_bank_accounts_kind'),
    sa.CheckConstraint("status IN ('active', 'ended')", name='ck_party_bank_accounts_status'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('party_bank_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_party_bank_accounts_party_id'), ['party_id'], unique=False)
        batch_op.create_index('uq_party_bank_accounts_one_default', ['party_id'], unique=True, postgresql_where=sa.text("is_default_payout AND status = 'active'"))

    op.create_table('party_contacts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('value', sa.String(length=150), nullable=False),
    sa.Column('value_normalised', sa.String(length=150), nullable=True),
    sa.Column('is_primary', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('email', 'mobile', 'phone')", name='ck_party_contacts_kind'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('party_contacts', schema=None) as batch_op:
        batch_op.create_index('ix_party_contacts_lookup', ['kind', 'value_normalised'], unique=False)
        batch_op.create_index(batch_op.f('ix_party_contacts_party_id'), ['party_id'], unique=False)

    op.create_table('party_identifiers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('id_type', sa.String(length=20), nullable=False),
    sa.Column('issuing_country', sa.String(length=2), server_default='KE', nullable=False),
    sa.Column('value_display', sa.String(length=50), nullable=False),
    sa.Column('value_normalised', sa.String(length=50), nullable=False),
    sa.Column('issued_on', sa.Date(), nullable=True),
    sa.Column('expires_on', sa.Date(), nullable=True),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("id_type IN ('national_id', 'passport', 'alien_id', 'kra_pin', 'company_reg_no')", name='ck_party_identifiers_type'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id_type', 'issuing_country', 'value_normalised', name='uq_party_identifiers_value'),
    sa.UniqueConstraint('party_id', 'id_type', name='uq_party_identifiers_one_per_type')
    )
    with op.batch_alter_table('party_identifiers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_party_identifiers_party_id'), ['party_id'], unique=False)

    op.create_table('party_mandates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('rule', sa.String(length=10), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='active', nullable=False),
    sa.Column('created_by', sa.String(length=120), nullable=False),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("rule <> 'custom' OR description IS NOT NULL", name='ck_party_mandates_custom_described'),
    sa.CheckConstraint("rule IN ('any_one', 'all', 'a_and_b', 'custom')", name='ck_party_mandates_rule'),
    sa.CheckConstraint("status IN ('active', 'ended')", name='ck_party_mandates_status'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('party_mandates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_party_mandates_party_id'), ['party_id'], unique=False)
        batch_op.create_index('uq_party_mandates_active', ['party_id'], unique=True, postgresql_where=sa.text("status = 'active'"))

    op.create_table('party_organisations',
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('legal_name', sa.String(length=200), nullable=False),
    sa.Column('trading_name', sa.String(length=200), nullable=True),
    sa.Column('registration_date', sa.Date(), nullable=True),
    sa.Column('org_type', sa.String(length=20), nullable=False),
    sa.Column('sector', sa.String(length=100), nullable=True),
    sa.Column('nature_of_business', sa.String(length=200), nullable=True),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("org_type IN ('sme', 'corporate', 'cooperative', 'ngo', 'investment_group', 'public_institution', 'sacco', 'church', 'fund_manager', 'insurer')", name='ck_party_organisations_type'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('party_id')
    )
    op.create_table('party_persons',
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('salutation', sa.String(length=20), nullable=True),
    sa.Column('first_name', sa.String(length=80), nullable=True),
    sa.Column('middle_name', sa.String(length=80), nullable=True),
    sa.Column('last_name', sa.String(length=80), nullable=True),
    sa.Column('gender', sa.String(length=10), nullable=True),
    sa.Column('date_of_birth', sa.Date(), nullable=True),
    sa.Column('marital_status', sa.String(length=10), nullable=True),
    sa.Column('nationality', sa.String(length=2), server_default='KE', nullable=False),
    sa.Column('residency', sa.String(length=10), server_default='local', nullable=False),
    sa.Column('sector', sa.String(length=100), nullable=True),
    sa.Column('nature_of_business', sa.String(length=200), nullable=True),
    sa.Column('employer_name', sa.String(length=150), nullable=True),
    sa.Column('employer_party_id', sa.Integer(), nullable=True),
    sa.Column('name_needs_review', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("gender IS NULL OR gender IN ('male', 'female', 'other')", name='ck_party_persons_gender'),
    sa.CheckConstraint("marital_status IS NULL OR marital_status IN ('single', 'married', 'divorced', 'widowed', 'other')", name='ck_party_persons_marital'),
    sa.CheckConstraint("residency IN ('local', 'foreign')", name='ck_party_persons_residency'),
    sa.ForeignKeyConstraint(['employer_party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('party_id')
    )
    op.create_table('party_relationships',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('from_party_id', sa.Integer(), nullable=False),
    sa.Column('to_party_id', sa.Integer(), nullable=False),
    sa.Column('relationship', sa.String(length=15), nullable=False),
    sa.Column('share_pct', sa.Numeric(precision=7, scale=4), nullable=True),
    sa.Column('kin_relationship', sa.String(length=50), nullable=True),
    sa.Column('signatory_list', sa.String(length=1), nullable=True),
    sa.Column('committed_amount', sa.Numeric(precision=20, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), server_default='KES', nullable=False),
    sa.Column('status', sa.String(length=10), server_default='active', nullable=False),
    sa.Column('started_on', sa.Date(), nullable=False),
    sa.Column('ended_on', sa.Date(), nullable=True),
    sa.Column('created_by', sa.String(length=120), nullable=False),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("committed_amount IS NULL OR (relationship = 'guarantor_of' AND committed_amount > 0)", name='ck_party_relationships_committed'),
    sa.CheckConstraint("currency = 'KES'", name='ck_party_relationships_currency_kes'),
    sa.CheckConstraint("relationship IN ('director', 'shareholder', 'signatory', 'next_of_kin', 'guarantor_of', 'related_party', 'referred_by')", name='ck_party_relationships_kind'),
    sa.CheckConstraint("signatory_list IS NULL OR signatory_list IN ('A', 'B')", name='ck_party_relationships_list'),
    sa.CheckConstraint("status IN ('active', 'ended')", name='ck_party_relationships_status'),
    sa.CheckConstraint('from_party_id <> to_party_id', name='ck_party_relationships_not_self'),
    sa.CheckConstraint('share_pct IS NULL OR (share_pct > 0 AND share_pct <= 100)', name='ck_party_relationships_share'),
    sa.ForeignKeyConstraint(['from_party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['to_party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('party_relationships', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_party_relationships_from_party_id'), ['from_party_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_party_relationships_to_party_id'), ['to_party_id'], unique=False)
        batch_op.create_index('uq_party_relationships_active', ['from_party_id', 'to_party_id', 'relationship'], unique=True, postgresql_where=sa.text("status = 'active'"))

    op.create_table('party_roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('party_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=15), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='active', nullable=False),
    sa.Column('started_on', sa.Date(), nullable=False),
    sa.Column('ended_on', sa.Date(), nullable=True),
    sa.Column('branch_id', sa.Integer(), nullable=True),
    sa.Column('date_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('investor', 'borrower', 'guarantor', 'director', 'shareholder', 'signatory', 'agent', 'next_of_kin')", name='ck_party_roles_role'),
    sa.CheckConstraint("status IN ('active', 'ended')", name='ck_party_roles_status'),
    sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('party_roles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_party_roles_party_id'), ['party_id'], unique=False)
        batch_op.create_index('uq_party_roles_active', ['party_id', 'role'], unique=True, postgresql_where=sa.text("status = 'active'"))

    op.execute(GUARD)
    conn = op.get_bind()
    for code, desc, sensitive, legacy in PERMISSIONS:
        conn.execute(sa.text("INSERT INTO permissions (code, module, description, sensitive) "
                             "VALUES (:c, 'parties', :d, :s)"), {'c': code, 'd': desc, 's': sensitive})
        conn.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT id, :c FROM roles "
                             "WHERE legacy_role = ANY(:l)"), {'c': code, 'l': list(legacy)})
    for request_type, levels, desc in POLICIES:
        conn.execute(sa.text("INSERT INTO approval_policies (request_type, levels, description) "
                             "VALUES (:t, CAST(:l AS jsonb), :d)"), {'t': request_type, 'l': json.dumps(levels), 'd': desc})
    for key, value, evidence in SEEDS:
        conn.execute(sa.text(
            "INSERT INTO setting_versions (key, value, effective_from, version_no, source, evidence, created_by,"
            " approved_by, approved_at) VALUES (:k, CAST(:v AS jsonb), :d, 1, 'working_assumption', :e,"
            " 'migration', 'docs/architecture/08-working-assumptions.md', now())"),
            {'k': key, 'v': json.dumps(value), 'd': SEED_DATE, 'e': evidence})


def downgrade():
    conn = op.get_bind()
    # setting_versions is insert-only; the trigger is lifted for this one cleanup.
    op.execute("ALTER TABLE setting_versions DISABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM setting_versions WHERE key = ANY(:k)"), {'k': [k for k, _, _ in SEEDS]})
    op.execute("ALTER TABLE setting_versions ENABLE TRIGGER trg_setting_versions_insert_only")
    conn.execute(sa.text("DELETE FROM approval_policies WHERE request_type = ANY(:t)"), {'t': [p[0] for p in POLICIES]})
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = ANY(:c)"), {'c': [p[0] for p in PERMISSIONS]})
    conn.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {'c': [p[0] for p in PERMISSIONS]})
    op.execute("DROP TRIGGER IF EXISTS trg_parties_no_delete ON parties")
    with op.batch_alter_table('party_roles', schema=None) as batch_op:
        batch_op.drop_index('uq_party_roles_active', postgresql_where=sa.text("status = 'active'"))
        batch_op.drop_index(batch_op.f('ix_party_roles_party_id'))

    op.drop_table('party_roles')
    with op.batch_alter_table('party_relationships', schema=None) as batch_op:
        batch_op.drop_index('uq_party_relationships_active', postgresql_where=sa.text("status = 'active'"))
        batch_op.drop_index(batch_op.f('ix_party_relationships_to_party_id'))
        batch_op.drop_index(batch_op.f('ix_party_relationships_from_party_id'))

    op.drop_table('party_relationships')
    op.drop_table('party_persons')
    op.drop_table('party_organisations')
    with op.batch_alter_table('party_mandates', schema=None) as batch_op:
        batch_op.drop_index('uq_party_mandates_active', postgresql_where=sa.text("status = 'active'"))
        batch_op.drop_index(batch_op.f('ix_party_mandates_party_id'))

    op.drop_table('party_mandates')
    with op.batch_alter_table('party_identifiers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_party_identifiers_party_id'))

    op.drop_table('party_identifiers')
    with op.batch_alter_table('party_contacts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_party_contacts_party_id'))
        batch_op.drop_index('ix_party_contacts_lookup')

    op.drop_table('party_contacts')
    with op.batch_alter_table('party_bank_accounts', schema=None) as batch_op:
        batch_op.drop_index('uq_party_bank_accounts_one_default', postgresql_where=sa.text("is_default_payout AND status = 'active'"))
        batch_op.drop_index(batch_op.f('ix_party_bank_accounts_party_id'))

    op.drop_table('party_bank_accounts')
    with op.batch_alter_table('party_addresses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_party_addresses_party_id'))

    op.drop_table('party_addresses')
    with op.batch_alter_table('parties', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_parties_home_branch_id'))

    op.drop_table('parties')
    op.execute("DROP FUNCTION IF EXISTS parties_refuse_delete()")
    op.execute("DROP SEQUENCE IF EXISTS party_no_seq")
