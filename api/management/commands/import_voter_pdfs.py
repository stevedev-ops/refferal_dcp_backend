import os
import pdfplumber
from django.core.management.base import BaseCommand
from api.models import VoterRecord


class Command(BaseCommand):
    help = 'Import voter register from IEBC PDF files (wipes existing data first)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--base-dir',
            type=str,
            default='2022_voter_register',
            help='Path to folder containing ward sub-folders with PDFs',
        )

    def handle(self, *args, **options):
        base_dir = options['base_dir']

        if not os.path.exists(base_dir):
            self.stdout.write(self.style.ERROR(f'Directory not found: {base_dir}'))
            return

        # 1. Wipe existing VoterRecord data
        self.stdout.write('Wiping existing VoterRecord data...')
        VoterRecord.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('Done. Starting fresh import from PDFs...'))

        total_count = 0
        batch = []
        BATCH_SIZE = 1000

        # 2. Walk all ward sub-folders
        for ward_folder in sorted(os.listdir(base_dir)):
            ward_path = os.path.join(base_dir, ward_folder)
            if not os.path.isdir(ward_path):
                continue

            # Derive a clean ward name from folder name
            ward_name = ward_folder.replace('_voter_register', '').replace('_', ' ').title()
            self.stdout.write(f'\nProcessing ward: {ward_name}')
            ward_count = 0

            for pdf_file in sorted(os.listdir(ward_path)):
                if not pdf_file.endswith('.pdf'):
                    continue

                pdf_path = os.path.join(ward_path, pdf_file)
                polling_station = None

                try:
                    with pdfplumber.open(pdf_path) as pdf:
                        for page in pdf.pages:
                            tables = page.extract_tables()
                            for table in tables:
                                if not table or len(table) < 2:
                                    continue

                                # Detect header row
                                header = [str(c).strip() if c else '' for c in table[0]]

                                # Extract polling station from the meta table (first table on page 1)
                                if 'POLLING CENTRE' in ' '.join(header).upper() or 'COUNTY' in ' '.join(header).upper():
                                    for cell in table[0]:
                                        if cell and 'POLLING CENTRE' in str(cell).upper():
                                            lines = str(cell).split('\n')
                                            for line in lines:
                                                if 'POLLING CENTRE' in line.upper():
                                                    polling_station = line.split(':', 1)[-1].strip()
                                    continue

                                # Detect the voter data table by its header
                                if 'Last Name' not in header and 'LAST NAME' not in [h.upper() for h in header]:
                                    continue

                                # Map column indices
                                try:
                                    id_idx = next(i for i, h in enumerate(header) if 'IDENTITY' in h.upper() or 'DOCUMENT' in h.upper())
                                    last_idx = next(i for i, h in enumerate(header) if 'LAST' in h.upper())
                                    first_idx = next(i for i, h in enumerate(header) if 'FIRST' in h.upper() or 'MIDDLE' in h.upper())
                                    dob_idx = next(i for i, h in enumerate(header) if 'DATE' in h.upper() or 'BIRTH' in h.upper())
                                except StopIteration:
                                    continue

                                for row in table[1:]:
                                    if not row or not row[last_idx]:
                                        continue

                                    last_name = str(row[last_idx]).strip().upper() if row[last_idx] else ''
                                    first_middle = str(row[first_idx]).strip().upper() if row[first_idx] else ''
                                    full_name = f"{first_middle} {last_name}".strip()

                                    raw_id = str(row[id_idx]).strip() if row[id_idx] else ''
                                    # Extract just the number part e.g. "ID 3******6" → "3******6"
                                    id_number = raw_id.replace('ID', '').replace('PP', '').strip()

                                    raw_dob = str(row[dob_idx]).strip() if row[dob_idx] else ''
                                    # DOB is year only (e.g. "1994")
                                    try:
                                        dob_year = int(raw_dob[:4]) if raw_dob else None
                                    except (ValueError, TypeError):
                                        dob_year = None

                                    if not full_name:
                                        continue

                                    batch.append(VoterRecord(
                                        id_number=id_number or None,
                                        full_name=full_name,
                                        date_of_birth=dob_year,
                                        ward=ward_name,
                                        polling_station=polling_station,
                                    ))
                                    ward_count += 1
                                    total_count += 1

                                    if len(batch) >= BATCH_SIZE:
                                        VoterRecord.objects.bulk_create(batch, ignore_conflicts=True)
                                        batch = []
                                        self.stdout.write(f'  Saved {total_count} records so far...')

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  Error processing {pdf_file}: {e}'))
                    continue

            self.stdout.write(f'  → {ward_count} records from {ward_name}')

        # Save remaining batch
        if batch:
            VoterRecord.objects.bulk_create(batch, ignore_conflicts=True)

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Import complete! Total VoterRecords in DB: {VoterRecord.objects.count()}'
        ))
