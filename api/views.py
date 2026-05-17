import csv
from django.http import HttpResponse
from rest_framework import status, views, response, generics
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count, Q
from .models import Member, Invite, VoterRecord
from .serializers import MemberSerializer, InviteSerializer, VoterRecordSerializer

from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser

from rest_framework.throttling import AnonRateThrottle

class LoginThrottle(AnonRateThrottle):
    scope = 'login'

def get_recursive_downline(member_id, depth_limit=10):
    """
    Returns a tuple of (all_member_ids, max_depth) for the given member's downline.
    """
    all_ids = set()
    max_d = 0
    stack = []
    
    # Get direct recruits first
    direct_recruits = Member.objects.filter(referred_by_id=member_id).values_list('id', flat=True)
    for rid in direct_recruits:
        stack.append((rid, 1))
        all_ids.add(rid)
        max_d = max(max_d, 1)

    while stack:
        mid, depth = stack.pop()
        if depth >= depth_limit:
            continue
            
        recruits = Member.objects.filter(referred_by_id=mid).values_list('id', flat=True)
        for rid in recruits:
            if rid not in all_ids:
                all_ids.add(rid)
                stack.append((rid, depth + 1))
                max_d = max(max_d, depth + 1)
                
    return list(all_ids), max_d

class MemberLoginView(views.APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]
    def post(self, request):
        try:
            first_name = request.data.get('firstName', '').strip()
            national_id = request.data.get('nationalId', '').strip()

            if not first_name or not national_id:
                return response.Response(
                    {"error": "First name and National ID are required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            member = Member.objects.filter(
                national_id=national_id,
                full_name__istartswith=first_name
            ).first()

            if not member:
                return response.Response(
                    {"error": "No member found with that First Name and ID combination."},
                    status=status.HTTP_404_NOT_FOUND
                )

            token, _ = Token.objects.get_or_create(user=member)
            return response.Response({
                "token": token.key,
                "member": MemberSerializer(member).data
            })
        except Exception as e:
            import traceback
            return response.Response({
                "error": "Debugging 500 error",
                "exception": str(e),
                "traceback": traceback.format_exc()
            }, status=500)

class MemberRegisterView(views.APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        data = request.data.copy()
        referrer_id = data.get('referred_by')
        invite_token = data.get('invite_token')
        
        # SECURITY FIX: Force is_admin to False for all public registrations
        data['is_admin'] = False
        data['is_staff'] = False
        data['is_superuser'] = False

        # 1. Quota & Depth Check
        if referrer_id and not invite_token:
            try:
                referrer = Member.objects.get(id=referrer_id)
                
                # Depth Check (Limit to 3 levels: Root -> L1 -> L2)
                # If referrer has a referrer (L1), and THAT person also has a referrer (L0), 
                # then the referrer is at L2 and cannot invite anyone else.
                if referrer.referred_by is not None and referrer.referred_by.referred_by is not None:
                    return response.Response(
                        {"error": "Maximum recruitment depth reached. Level 2 members cannot invite others."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                quota = 25 if referrer.referred_by is None else 5
                current_count = referrer.recruits.count()
                if current_count >= quota:
                    return response.Response(
                        {"error": f"Recruiter has reached their quota of {quota} members."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Member.DoesNotExist:
                return response.Response({"error": "Invalid referrer."}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Duplicate Check
        if Member.objects.filter(Q(phone=data.get('phone')) | Q(national_id=data.get('national_id'))).exists():
            return response.Response(
                {"error": "Phone or ID already registered."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Invite Token Check
        if invite_token:
            try:
                invite = Invite.objects.get(id=invite_token)
                if invite.is_used:
                    return response.Response({"error": "Invite already used."}, status=status.HTTP_400_BAD_REQUEST)
                invite.is_used = True
                invite.save()
            except (Invite.DoesNotExist, ValueError):
                return response.Response({"error": "Invalid invite code."}, status=status.HTTP_400_BAD_REQUEST)

        # 4. Create Member
        serializer = MemberSerializer(data=data)
        if serializer.is_valid():
            member = serializer.save()

            # Voter Verification: match full_name + year of birth against voter register
            is_verified = False
            if member.yob:
                name_parts = [p for p in member.full_name.upper().split() if len(p) > 2]
                # Get candidates with matching DOB year first (much smaller set)
                candidates = VoterRecord.objects.filter(date_of_birth=member.yob)
                import re
                for record in candidates:
                    record_name_upper = record.full_name.upper()
                    record_words = set(re.split(r'[-\s]+', record_name_upper))
                    matched_parts = sum(1 for part in name_parts if part in record_words)
                    
                    # Require at least 2 full name parts to match exactly
                    if matched_parts >= 2:
                        is_verified = True
                        member.is_voter_verified = True
                        # Store official IEBC data
                        member.official_ward = record.ward
                        member.official_polling_station = record.polling_station
                        member.save()
                        break

            token, _ = Token.objects.get_or_create(user=member)
            return response.Response({
                "token": token.key,
                "member": MemberSerializer(member).data
            }, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MemberMeView(views.APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return response.Response(MemberSerializer(request.user).data)

class MemberPublicView(views.APIView):
    permission_classes = [AllowAny]
    def get(self, request, pk):
        try:
            member = Member.objects.get(pk=pk)
            return response.Response({
                "id": member.id,
                "full_name": member.full_name
            })
        except Member.DoesNotExist:
            return response.Response({"error": "Member not found"}, status=status.HTTP_404_NOT_FOUND)

class MemberInsightsView(views.APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, pk):
        if not request.user.is_admin and request.user.id != int(pk):
            return response.Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            member = Member.objects.get(pk=pk)
        except Member.DoesNotExist:
            return response.Response({"error": "Member not found"}, status=status.HTTP_404_NOT_FOUND)

        # Lineage (Walking up)
        lineage = []
        curr = member
        while curr:
            lineage.insert(0, MemberSerializer(curr).data)
            curr = curr.referred_by
            if len(lineage) > 10: break # Safety break

        # Network Size & Depth (Recursive)
        network_ids, network_depth = get_recursive_downline(member.id)
        
        return response.Response({
            "member_id": member.id,
            "tier": len(lineage),
            "network_size": len(network_ids),
            "network_depth": network_depth,
            "direct_invites": member.recruits.count(),
            "lineage": lineage,
            "direct_inviter": lineage[-2] if len(lineage) > 1 else None,
            "top_mobilizer": lineage[0] if lineage else None
        })

class MemberListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Member.objects.all().order_by('-id')
    serializer_class = MemberSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        referred_by = self.request.query_params.get('referred_by')
        if referred_by:
            if referred_by == 'null':
                queryset = queryset.filter(referred_by__isnull=True)
            else:
                queryset = queryset.filter(referred_by=referred_by)

        downline_of = self.request.query_params.get('downline_of')
        if downline_of:
            downline_ids, _ = get_recursive_downline(downline_of)
            queryset = queryset.filter(id__in=downline_ids)

        # ALWAYS filter out admins and staff from the public member lists
        queryset = queryset.filter(is_admin=False, is_staff=False)

        if not self.request.user.is_admin:
            # Regular users can only see their direct recruits
            queryset = queryset.filter(referred_by=self.request.user)
        
        search = self.request.query_params.get('search')
        if search:
            search_parts = [p.strip() for p in search.split() if len(p.strip()) > 1]
            if search_parts:
                query = Q()
                for part in search_parts:
                    query &= Q(full_name__icontains=part)
                
                # Allow searching by ID if only one part is provided
                if len(search_parts) == 1:
                    query |= Q(national_id__icontains=search)
                
                queryset = queryset.filter(query)
            else:
                queryset = queryset.filter(national_id__icontains=search)
        
        ward = self.request.query_params.get('ward')
        if ward:
            queryset = queryset.filter(ward__iexact=ward)
        
        voter_status = self.request.query_params.get('voter_status', '').lower()
        if voter_status == 'verified':
            queryset = queryset.filter(is_voter_verified=True)
        elif voter_status == 'unverified':
            queryset = queryset.filter(is_voter_verified=False)
            
        sort = self.request.query_params.get('sort')
        if sort == 'voter_status':
            queryset = queryset.order_by('-is_voter_verified', '-id')
        elif sort == 'voter_status_asc':
            queryset = queryset.order_by('is_voter_verified', '-id')
            
        return queryset
class MemberDetailView(views.APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        try:
            member = Member.objects.get(pk=pk)
            return response.Response(MemberSerializer(member).data)
        except Member.DoesNotExist:
            return response.Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, pk):
        """Only allows updating referred_by (for Promote to Root feature)."""
        try:
            member = Member.objects.get(pk=pk)
        except Member.DoesNotExist:
            return response.Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        allowed_fields = {'referred_by'}
        data = {k: v for k, v in request.data.items() if k in allowed_fields}

        if 'referred_by' in data:
            val = data['referred_by']
            if val is None or val == 'null' or val == '':
                member.referred_by = None
            else:
                try:
                    member.referred_by = Member.objects.get(pk=val)
                except Member.DoesNotExist:
                    return response.Response({"error": "Referrer not found"}, status=status.HTTP_400_BAD_REQUEST)

        member.save()
        return response.Response(MemberSerializer(member).data)

class VoterRecordPagination(PageNumberPagination):
    page_size = 50

class VoterRecordListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    queryset = VoterRecord.objects.all().order_by('full_name')
    serializer_class = VoterRecordSerializer
    pagination_class = VoterRecordPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            search_parts = [p.strip() for p in search.split() if len(p.strip()) > 1]
            if search_parts:
                query = Q()
                for part in search_parts:
                    query &= Q(full_name__icontains=part)
                
                # Also allow searching by ID or phone if only one part is provided
                if len(search_parts) == 1:
                    query |= Q(id_number__icontains=search) | Q(phone_number__icontains=search)
                
                queryset = queryset.filter(query)
            else:
                queryset = queryset.filter(
                    Q(id_number__icontains=search) | Q(phone_number__icontains=search)
                )
        
        ward = self.request.query_params.get('ward')
        if ward:
            queryset = queryset.filter(ward__icontains=ward)
            
        return queryset

class ReportStatsView(views.APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        member_id = request.query_params.get('member_id')
        mode = request.query_params.get('mode', 'all')  # all | verified | unverified

        base_qs = Member.objects.filter(is_admin=False, is_staff=False)
        if member_id:
            downline_ids, _ = get_recursive_downline(member_id)
            # Include direct recruits AND their downline
            base_qs = base_qs.filter(id__in=downline_ids)

        if mode == 'verified':
            queryset = base_qs.filter(is_voter_verified=True)
            ward_field = 'official_ward'
            station_field = 'official_polling_station'
        elif mode == 'unverified':
            queryset = base_qs.filter(is_voter_verified=False)
            ward_field = 'ward'
            station_field = 'polling_station'
        else:  # all
            queryset = base_qs
            ward_field = 'ward'
            station_field = 'polling_station'

        ward_summary = queryset.values(ward_field).annotate(count=Count('id')).order_by('-count')
        polling_summary = queryset.values(station_field, ward_field).annotate(count=Count('id')).order_by('-count')

        ward_res = [{"ward": item[ward_field] or "Unknown", "count": item['count']} for item in ward_summary]
        polling_res = [
            {
                "station": item[station_field] or "Unknown",
                "ward": item[ward_field] or "Unknown",
                "count": item['count']
            }
            for item in polling_summary
        ]

        return response.Response({
            "ward_summary": ward_res,
            "polling_summary": polling_res,
            "total": queryset.count(),
            "mode": mode,
        })

class SystemStatsView(views.APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        total = Member.objects.filter(is_admin=False, is_staff=False).count()
        roots = Member.objects.filter(referred_by__isnull=True, is_admin=False, is_staff=False).count()
        verified = Member.objects.filter(is_voter_verified=True, is_admin=False, is_staff=False).count()
        unverified = total - verified
        
        return response.Response({
            "total_registered": total,
            "total_roots": roots,
            "verified_voters": verified,
            "unverified_new": unverified,
        })

class InviteCreateView(generics.CreateAPIView):
    permission_classes = [IsAdminUser]
    queryset = Invite.objects.all()
    serializer_class = InviteSerializer

class InviteDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    queryset = Invite.objects.all()
    serializer_class = InviteSerializer
    lookup_field = 'id'

class MemberDownlineExportView(views.APIView):
    permission_classes = [IsAdminUser]
    
    def get(self, request, pk):
        status_filter = request.query_params.get('status', 'all')
        try:
            root_member = Member.objects.get(pk=pk)
        except Member.DoesNotExist:
            return response.Response({"error": "Member not found"}, status=status.HTTP_404_NOT_FOUND)
            
        response_csv = HttpResponse(content_type='text/csv')
        filename = f"downline_{status_filter}_{root_member.full_name.replace(' ', '_')}.csv"
        response_csv['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response_csv)
        writer.writerow(['Level', 'Full Name', 'Phone', 'National ID', 'Ward', 'Polling Station', 'Verified?', 'Recruited By', 'Date Joined'])
        
        # DFS traversal for hierarchical structure
        stack = [(root_member, 0, "ROOT")]
        seen = {root_member.id}
        
        while stack:
            curr, depth, recruiter_name = stack.pop()
            
            # Check if current member should be included in CSV
            is_root = curr.id == root_member.id
            should_include = True
            if status_filter == 'verified' and not curr.is_voter_verified and not is_root:
                should_include = False
            elif status_filter == 'unverified' and curr.is_voter_verified and not is_root:
                should_include = False

            if should_include:
                prefix = "  " * depth + ("↳ " if depth > 0 else "")
                writer.writerow([
                    depth,
                    f"{prefix}{curr.full_name}",
                    curr.phone,
                    curr.national_id,
                    curr.ward,
                    curr.polling_station,
                    "YES" if curr.is_voter_verified else "NO",
                    recruiter_name,
                    curr.created_at.strftime('%Y-%m-%d')
                ])
            
            if depth < 15:
                # Get recruits in reverse order to maintain correct DFS order when popping
                recruits = Member.objects.filter(referred_by=curr).order_by('-created_at')
                for r in recruits:
                    if r.id not in seen:
                        seen.add(r.id)
                        stack.append((r, depth + 1, curr.full_name))
                        
        return response_csv
