# Инициализация LDAP сервера

Производится один раз, после первого запуска контейнера.

```sh
cd .utils/ldap
docker cp init-ds1.sh artstore_ldap:/init-ds1.sh
docker exec -it artstore_ldap sh init-ds1.sh
docker restart artstore_ldap
```

Ждем перезапуск контейнера

```sh
docker cp init-ds2.sh artstore_ldap:/init-ds2.sh
docker exec -it artstore_ldap sh init-ds2.sh
```
