from rest_framework import serializers
from .models import Member, Invite, VoterRecord

class MemberSerializer(serializers.ModelSerializer):
    referral_code = serializers.ReadOnlyField()
    recruits_count = serializers.SerializerMethodField()
    referrer_name = serializers.CharField(source='referred_by.full_name', read_only=True)

    class Meta:
        model = Member
        fields = [
            'id', 'full_name', 'phone', 'national_id', 'email', 'yob',
            'ward', 'polling_station',
            'official_ward', 'official_polling_station',
            'referral_code', 'referred_by', 'is_voter_verified', 'created_at',
            'recruits_count', 'referrer_name', 'is_admin', 'is_staff'
        ]

    def get_recruits_count(self, obj):
        return obj.recruits.count()

class InviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invite
        fields = ['id', 'target_role', 'is_used', 'created_at']

class VoterRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = VoterRecord
        fields = ['id', 'id_number', 'phone_number', 'full_name', 'ward', 'polling_station', 'created_at']
