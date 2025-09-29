#/bin/bash


ldapadd -H ldap://localhost:3389 -D "cn=Directory Manager" -w 'password' << EOF
dn: ou=Groups,dc=artstore,dc=local
objectClass: organizationalunit
objectClass: top
ou: Groups
aci: (targetattr="cn || member || gidNumber || description || objectClass")(targetfilter="(objectClass=groupOfUniqueNames)")(version 3.0; acl "Enable group_admin to manage groups"; allow (write, add, delete)(groupdn="ldap:///cn=group_admin,ou=permissions,dc=artstore,dc=local");)
aci: (targetattr="cn || member || memberUid || gidNumber || nsUniqueId || description || objectClass")(targetfilter="(objectClass=groupOfUniqueNames)")(version 3.0; acl "Enable anyone group read"; allow (read, search, compare)(userdn="ldap:///anyone");)
aci: (targetattr="member")(targetfilter="(objectClass=groupOfUniqueNames)")(version 3.0; acl "Enable group_modify to alter members"; allow (write)(groupdn="ldap:///cn=group_modify,ou=permissions,dc=artstore,dc=local");)

dn: ou=People,dc=artstore,dc=local
objectClass: organizationalunit
objectClass: top
ou: People
aci: (targetattr="displayName || legalName || userPassword || nsSshPublicKey")(version 3.0; acl "Enable self partial modify"; allow (write)(userdn="ldap:///self");)
aci: (targetattr="legalName || telephoneNumber || mobile || sn")(targetfilter="(|(objectClass=nsPerson)(objectClass=inetOrgPerson))")(version 3.0; acl "Enable self legalname read"; allow (read, search, compare)(userdn="ldap:///self");)
aci: (targetattr="legalName || telephoneNumber")(targetfilter="(objectClass=nsPerson)")(version 3.0; acl "Enable user legalname read"; allow (read, search, compare)(groupdn="ldap:///cn=user_private_read,ou=permissions,dc=artstore,dc=local");)
aci: (targetattr="objectClass || description || nsUniqueId || uid || displayName || loginShell || uidNumber || gidNumber || gecos || homeDirectory || cn || memberOf || mail || nsSshPublicKey || nsAccountLock || userCertificate")(targetfilter="(objectClass=posixaccount)")(version 3.0; acl "Enable anyone user read"; allow (read, search, compare)(userdn="ldap:///anyone");)
aci: (targetattr="uid || description || displayName || loginShell || uidNumber || gidNumber || gecos || homeDirectory || cn || memberOf || mail || legalName || telephoneNumber || mobile")(targetfilter="(&(objectClass=nsPerson)(objectClass=nsAccount))")(version 3.0; acl "Enable user admin create"; allow (write, add, delete, read)(groupdn="ldap:///cn=user_admin,ou=permissions,dc=artstore,dc=local");)
aci: (targetattr="uid || description || displayName || loginShell || uidNumber || gidNumber || gecos || homeDirectory || cn || memberOf || mail || legalName || telephoneNumber || mobile")(targetfilter="(&(objectClass=nsPerson)(objectClass=nsAccount))")(version 3.0; acl "Enable user modify to change users"; allow (write, read)(groupdn="ldap:///cn=user_modify,ou=permissions,dc=artstore,dc=local");)
aci: (targetattr="userPassword || nsAccountLock || userCertificate || nsSshPublicKey")(targetfilter="(objectClass=nsAccount)")(version 3.0; acl "Enableuser password reset"; allow (write, read)(groupdn="ldap:///cn=user_passwd_reset,ou=permissions,dc=artstore,dc=local");)

dn: uid=ldap_admin,ou=People,dc=artstore,dc=local
objectClass: inetOrgPerson
objectClass: organizationalPerson
objectClass: person
objectClass: top
cn: Admin
sn: Test
displayName: Test LDAP admin
uid: ldap_admin
mail: ldap_admin@artstore.local
userPassword: {SSHA512}AsZkWA367HhmiXQ5Si6H5TPAdmZw485g8lcCbwnm70s9xpTzUxw8VKxhJpAMqTIp9aNhkgWiO/3a5vs8ekJwjUYaR5usop6V

dn: uid=ldap_user,ou=People,dc=artstore,dc=local
objectClass: inetOrgPerson
objectClass: organizationalPerson
objectClass: person
objectClass: top
cn: User
sn: Test
displayName: Test LDAP user
uid: ldap_user
mail: ldap_user@artstore.local
userPassword: {SSHA512}AsZkWA367HhmiXQ5Si6H5TPAdmZw485g8lcCbwnm70s9xpTzUxw8VKxhJpAMqTIp9aNhkgWiO/3a5vs8ekJwjUYaR5usop6V


dn: cn=admins,ou=Groups,dc=artstore,dc=local
objectClass: groupOfUniqueNames
objectClass: top
cn: admins
uniqueMember: uid=ldap_admin,ou=People,dc=artstore,dc=local

dn: cn=users,ou=Groups,dc=artstore,dc=local
objectClass: groupOfUniqueNames
objectClass: top
cn: users
uniqueMember: uid=ldap_user,ou=People,dc=artstore,dc=local
EOF