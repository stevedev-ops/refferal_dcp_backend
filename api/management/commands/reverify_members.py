from django.core.management.base import BaseCommand
import re
from api.models import Member, VoterRecord

class Command(BaseCommand):
    help = 'Re-run voter verification for all members'

    def handle(self, *args, **options):
        self.stdout.write("Starting re-verification of all members...")
        members = Member.objects.all()
        count_verified = 0
        count_unverified = 0
        
        for member in members:
            # Reset verification status first
            old_status = member.is_voter_verified
            member.is_voter_verified = False
            member.official_ward = None
            member.official_polling_station = None
            
            is_verified = False
            if member.yob:
                name_parts = [p for p in member.full_name.upper().split() if len(p) > 2]
                # Get candidates with matching DOB year
                candidates = VoterRecord.objects.filter(date_of_birth=member.yob)
                
                for record in candidates:
                    record_name_upper = record.full_name.upper()
                    record_words = set(re.split(r'[-\s]+', record_name_upper))
                    matched_parts = sum(1 for part in name_parts if part in record_words)
                    
                    # Require at least 2 full name parts to match exactly
                    if matched_parts >= 2:
                        is_verified = True
                        member.is_voter_verified = True
                        member.official_ward = record.ward
                        member.official_polling_station = record.polling_station
                        break
            
            member.save()
            
            if member.is_voter_verified:
                count_verified += 1
            else:
                count_unverified += 1
                
            if old_status != member.is_voter_verified:
                status_str = "VERIFIED" if member.is_voter_verified else "UNVERIFIED"
                self.stdout.write(self.style.SUCCESS(f"Member '{member.full_name}' (ID: {member.national_id}) changed to {status_str}"))

        self.stdout.write(self.style.SUCCESS("\nVerification Complete."))
        self.stdout.write(f"Total Members: {members.count()}")
        self.stdout.write(f"Verified: {count_verified}")
        self.stdout.write(f"Unverified: {count_unverified}")
