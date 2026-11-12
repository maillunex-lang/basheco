-- Preserve the existing audit allowlist and add the new starter-grant event.
ALTER TABLE security_audit DROP CONSTRAINT security_audit_event_type_check;
ALTER TABLE security_audit ADD CONSTRAINT security_audit_event_type_check CHECK (
 event_type IN ('account.registered','auth.login','auth.logout','company.created','wallet.transfer','alpha.starter_granted')
);
