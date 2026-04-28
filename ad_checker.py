import ldap3
from ldap3 import Server, Connection, ALL, SUBTREE
import config

class ADChecker:
    def __init__(self):
        self.server = Server(config.AD_SERVER, get_info=ALL)
        self.conn = Connection(
            self.server, 
            user=config.AD_USER, 
            password=config.AD_PASSWORD,
            auto_bind=True
        )
    
    def get_users_from_group(self):
        group_dn = config.MONITOR_GROUP_DN
        
        # Сначала получаем членов группы
        self.conn.search(
            search_base=group_dn,
            search_filter='(objectClass=group)',
            search_scope=ldap3.BASE,
            attributes=['member']
        )
        
        members = []
        if self.conn.entries:
            member_dns = self.conn.entries[0].member.values if hasattr(self.conn.entries[0], 'member') else []
            
            # Для каждого члена группы получаем информацию
            for member_dn in member_dns:
                self.conn.search(
                    search_base=member_dn,
                    search_filter='(objectClass=user)',
                    search_scope=ldap3.BASE,
                    attributes=['sAMAccountName', 'mail', 'displayName']
                )
                
                if self.conn.entries:
                    entry = self.conn.entries[0]
                    username = str(entry.sAMAccountName) if hasattr(entry, 'sAMAccountName') else ''
                    email = str(entry.mail) if hasattr(entry, 'mail') and entry.mail else ''
                    display_name = str(entry.displayName) if hasattr(entry, 'displayName') and entry.displayName else username
                    
                    members.append({
                        'username': username,
                        'email': email,
                        'display_name': display_name,
                        'dn': member_dn
                    })
        
        return members
    
    def close(self):
        self.conn.unbind()
