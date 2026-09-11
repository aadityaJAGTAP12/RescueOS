#!/usr/bin/env python3
import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.data.models import Need, ResourceOffer, Operation
from agent.data.repository import get_repository

DEMO_NEEDS = [
    Need('need_jorhat_crit_1', need_type='rescue', title='Severe flood water rescue near Nimati Ghat', description='35 villagers stranded on high embankment with rising Brahmaputra water. 2 rescue boats required immediately.', district_id='jorhat', lat=26.8625, lon=94.2150, location_name='Nimati Ghat, Jorhat', urgency='critical', status='OPEN', requested_resources=[{'resource_type': 'boat', 'quantity': 2, 'unit': 'units'}]),
    Need('need_jorhat_crit_2', need_type='medical', title='Medical emergency & antivenom needed at Camp B', description='Flood evacuees report multiple snakebite incidents and acute water-borne illnesses. Critical medical team requested.', district_id='jorhat', lat=26.7450, lon=94.2180, location_name='Camp B, Jorhat', urgency='critical', status='RESPONDING', requested_resources=[{'resource_type': 'medical_team', 'quantity': 1, 'unit': 'people'}]),
    Need('need_jorhat_high_1', need_type='water', title='Clean drinking water required at Titabar Shelter', description='Over 400 displaced residents without potable water source. Need 2000 liters of bottled water or mobile purification unit.', district_id='jorhat', lat=26.5867, lon=94.1956, location_name='Titabar Shelter, Jorhat', urgency='high', status='OPEN', requested_resources=[{'resource_type': 'water', 'quantity': 2000, 'unit': 'liters'}]),
    Need('need_jorhat_high_2', need_type='food', title='Baby food and dry rations at Teok Community Hall', description='150 families with infants cut off from grocery supplies. Ready-to-eat baby food and dry ration kits needed.', district_id='jorhat', lat=26.8378, lon=94.4258, location_name='Teok Community Hall, Jorhat', urgency='high', status='RESPONDING', requested_resources=[{'resource_type': 'food', 'quantity': 150, 'unit': 'kits'}]),
    Need('need_jorhat_med_1', need_type='shelter', title='Temporary tarpaulins needed in Mariani relief camp', description='Heavy monsoon rain leaking through temporary shelter roofs. 60 waterproof tarpaulin sheets required.', district_id='jorhat', lat=26.6625, lon=94.3217, location_name='Mariani Camp, Jorhat', urgency='medium', status='OPEN', requested_resources=[{'resource_type': 'shelter', 'quantity': 60, 'unit': 'units'}]),
    Need('need_jorhat_low_1', need_type='other', title='Flashlights and hygiene kits requested at Borbheta', description='Power outage in evacuation area. Emergency solar flashlights and sanitation kits requested.', district_id='jorhat', lat=26.7350, lon=94.2000, location_name='Borbheta, Jorhat', urgency='low', status='RESOLVED', requested_resources=[{'resource_type': 'other', 'quantity': 50, 'unit': 'kits'}]),

    Need('need_sivasagar_crit_1', need_type='rescue', title='Dikhow river embankment breach rescue near Nazira', description='Breached embankment has flooded low-lying residential sectors. Emergency evacuation for 60 individuals.', district_id='sivasagar', lat=26.9167, lon=94.7333, location_name='Nazira, Sivasagar', urgency='critical', status='OPEN', requested_resources=[{'resource_type': 'boat', 'quantity': 3, 'unit': 'units'}]),
    Need('need_sivasagar_high_1', need_type='medical', title='Emergency insulin and first aid kits near Amguri', description='Chronic medication depleted for diabetic evacuees at relief post. Cold-storage medical delivery needed.', district_id='sivasagar', lat=26.8111, lon=94.5306, location_name='Amguri, Sivasagar', urgency='high', status='OPEN', requested_resources=[{'resource_type': 'medicine', 'quantity': 25, 'unit': 'kits'}]),
    Need('need_sivasagar_med_1', need_type='food', title='500 food packets required at Sivasagar Girls College', description='Central relief station serving 500 hot meals daily requires dry grains and cooking oil replenishment.', district_id='sivasagar', lat=26.9826, lon=94.6425, location_name='Sivasagar Town', urgency='medium', status='RESPONDING', requested_resources=[{'resource_type': 'food', 'quantity': 500, 'unit': 'kg'}]),
    Need('need_sivasagar_low_1', need_type='shelter', title='Blankets distribution at Demow school', description='Distribution of 100 blankets for elderly residents complete.', district_id='sivasagar', lat=27.1333, lon=94.7500, location_name='Demow, Sivasagar', urgency='low', status='RESOLVED', requested_resources=[{'resource_type': 'shelter', 'quantity': 100, 'unit': 'units'}]),

    Need('need_charaideo_crit_1', need_type='rescue', title='Flash flood evacuation near Sonari tea estate', description='Rapid runoff from foothills has surrounded worker quarters. 4x4 or raft evacuation needed.', district_id='charaideo', lat=27.0258, lon=95.0167, location_name='Sonari, Charaideo', urgency='critical', status='OPEN', requested_resources=[{'resource_type': 'boat', 'quantity': 2, 'unit': 'units'}]),
    Need('need_charaideo_high_1', need_type='medical', title='Medical team needed for injured villagers at Moranhat', description='Structural collapse injuries following landslide. Mobile trauma surgical team requested.', district_id='charaideo', lat=27.1833, lon=94.9333, location_name='Moranhat, Charaideo', urgency='high', status='OPEN', requested_resources=[{'resource_type': 'medical_team', 'quantity': 1, 'unit': 'people'}]),
    Need('need_charaideo_med_1', need_type='food', title='Dry rations for 120 families at Charaideo Maidam', description='Community camp sheltering 120 families requires rice, lentils, and safe drinking water.', district_id='charaideo', lat=26.9389, lon=94.9083, location_name='Charaideo Maidam', urgency='medium', status='RESPONDING', requested_resources=[{'resource_type': 'food', 'quantity': 120, 'unit': 'kits'}]),
    Need('need_charaideo_low_1', need_type='other', title='Solar lanterns at Sapekhati camp', description='Lighting installed successfully across refugee perimeter.', district_id='charaideo', lat=27.1167, lon=95.1500, location_name='Sapekhati, Charaideo', urgency='low', status='RESOLVED', requested_resources=[{'resource_type': 'other', 'quantity': 30, 'unit': 'units'}]),

    Need('need_golaghat_crit_1', need_type='rescue', title='Dhansiri river flooding — stranded families in Bokakhat', description='Water level breached residential perimeter. 50 families cut off on rooftops near Kaziranga fringe.', district_id='golaghat', lat=26.6333, lon=93.6000, location_name='Bokakhat, Golaghat', urgency='critical', status='OPEN', requested_resources=[{'resource_type': 'boat', 'quantity': 4, 'unit': 'units'}]),
    Need('need_golaghat_high_1', need_type='water', title='Water purification tablets at Golaghat Town Hall', description='Municipal water supply submerged. 5000 halogen water purification tablets needed immediately.', district_id='golaghat', lat=26.5167, lon=93.9667, location_name='Golaghat Town', urgency='high', status='OPEN', requested_resources=[{'resource_type': 'water', 'quantity': 5000, 'unit': 'units'}]),
    Need('need_golaghat_med_1', need_type='food', title='Cooked meal packets needed at Dergaon shelter', description='Community kitchen serving 300 flood victims daily requires ration supplies.', district_id='golaghat', lat=26.7000, lon=93.9667, location_name='Dergaon, Golaghat', urgency='medium', status='RESPONDING', requested_resources=[{'resource_type': 'food', 'quantity': 300, 'unit': 'kits'}]),
    Need('need_golaghat_low_1', need_type='other', title='Sanitary kits at Sarupathar school', description='Essential hygiene and female sanitation kits distributed to all occupants.', district_id='golaghat', lat=26.1833, lon=93.8167, location_name='Sarupathar, Golaghat', urgency='low', status='RESOLVED', requested_resources=[{'resource_type': 'other', 'quantity': 80, 'unit': 'kits'}]),
]

DEMO_OFFERS = [
    ResourceOffer('offer_jorhat_boats', organization_id='org_reliefos_default', resource_type='boat', quantity=4, unit='units', lat=26.7509, lon=94.2037, location_name='Jorhat Staging Area', district_id='jorhat', status='OFFERED', notes='4 motorized rubber dinghies with certified rescue operators.'),
    ResourceOffer('offer_jorhat_food', organization_id='org_reliefos_default', resource_type='food', quantity=500, unit='kg', lat=26.7550, lon=94.2100, location_name='Jorhat Central Warehouse', district_id='jorhat', status='AVAILABLE', notes='High-energy biscuits, packaged drinking water, and dry rations.'),
    ResourceOffer('offer_sivasagar_boats', organization_id='org_reliefos_default', resource_type='boat', quantity=2, unit='units', lat=26.9826, lon=94.6425, location_name='Sivasagar District Depot', district_id='sivasagar', status='OFFERED', notes='2 rapid response flood boats with life jackets.'),
    ResourceOffer('offer_golaghat_med', organization_id='org_reliefos_default', resource_type='medical_team', quantity=2, unit='people', lat=26.5167, lon=93.9667, location_name='Golaghat Civil Hospital', district_id='golaghat', status='ACCEPTED', notes='Emergency medical triage team with portable trauma equipment.'),
]

DEMO_OPERATIONS = [
    Operation('op_nimati_rescue', name='Operation Nimati Rescue', operation_type='rescue', description='Coordinated boat rescue for 35 stranded residents along Nimati Brahmaputra bank.', need_id='need_jorhat_crit_1', lead_organization_id='org_reliefos_default', district_id='jorhat', lat=26.8625, lon=94.2150, location_name='Nimati Ghat, Jorhat', status='ACTIVE'),
    Operation('op_titabar_water', name='Titabar Clean Water Transport', operation_type='supply_delivery', description='Mobilizing water tankers and packaged water boxes to Titabar community camp.', need_id='need_jorhat_high_1', lead_organization_id='org_reliefos_default', district_id='jorhat', lat=26.5867, lon=94.1956, location_name='Titabar Shelter, Jorhat', status='PLANNING'),
    Operation('op_nazira_evac', name='Nazira Embankment Evacuation', operation_type='evacuation', description='Evacuating affected households along breached Dikhow river channel.', need_id='need_sivasagar_crit_1', lead_organization_id='org_reliefos_default', district_id='sivasagar', lat=26.9167, lon=94.7333, location_name='Nazira, Sivasagar', status='ACTIVE'),
    Operation('op_bokakhat_rescue', name='Bokakhat Flood Relief Operation', operation_type='rescue', description='Joint deployment of rescue boats and medical first responders.', need_id='need_golaghat_crit_1', lead_organization_id='org_reliefos_default', district_id='golaghat', lat=26.6333, lon=93.6000, location_name='Bokakhat, Golaghat', status='ACTIVE'),
]

def seed_operational_data():
    repo = get_repository()
    print(f'[SEED] Repository: {type(repo).__name__}')
    for need in DEMO_NEEDS:
        try:
            repo.create_need(need)
        except Exception:
            try:
                repo.update_need(need)
            except Exception:
                pass
    print(f'  [OK] {len(DEMO_NEEDS)} Needs seeded.')

    for offer in DEMO_OFFERS:
        try:
            repo.create_resource_offer(offer)
        except Exception:
            try:
                repo.update_resource_offer(offer)
            except Exception:
                pass
    print(f'  [OK] {len(DEMO_OFFERS)} Offers seeded.')

    for op in DEMO_OPERATIONS:
        try:
            repo.create_operation(op)
        except Exception:
            try:
                repo.update_operation(op)
            except Exception:
                pass
    print(f'  [OK] {len(DEMO_OPERATIONS)} Operations seeded.')

if __name__ == '__main__':
    seed_operational_data()
