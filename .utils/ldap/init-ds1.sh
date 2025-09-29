#! /bin/bash
# Инициализация суффикса и плагина
# После инициализации плагина - требуется рестарт контейнера

dsconf ldap://localhost:3389 -D 'cn=Directory Manager' -w 'password' backend create --suffix 'dc=artstore,dc=local' --be-name userroot --create-suffix 

ldapmodify -H ldap://localhost:3389 -D "cn=Directory Manager" -w 'password' << EOF
dn: cn=Retro Changelog Plugin,cn=plugins,cn=config
changetype: modify
replace: nsslapd-pluginEnabled
nsslapd-pluginEnabled: on
-

dn: cn=MemberOf Plugin,cn=plugins,cn=config
changetype: modify
replace: nsslapd-pluginEnabled
nsslapd-pluginEnabled: on
-
replace: memberofgroupattr
memberofgroupattr: uniqueMember
EOF
