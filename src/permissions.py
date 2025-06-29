from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from app.models import *
from billing.models import *
from reference.models import *
from bareme.models import *
from groupage.models import *

def create_export_permissions():
    """Create export permissions for all models if they don't already exist"""
    
    def create_permission_if_not_exists(model, codename, name):
        content_type = ContentType.objects.get_for_model(model)
        try:
            Permission.objects.get_or_create(
                codename=codename,
                name=name,
                content_type=content_type,
            )
        except Exception as e:
            print(f"Error creating permission {codename} for {model.__name__}: {str(e)}")

    # App Models
    create_permission_if_not_exists(Tc, "can_export_tc", "Can export containers")
    create_permission_if_not_exists(BulletinsEscort, "can_export_bulletin", "Can export bulletins")
    create_permission_if_not_exists(Visite, "can_export_visite", "Can export inspections")
    create_permission_if_not_exists(Gros, "can_export_gros", "Can export MRNs")
    create_permission_if_not_exists(Article, "can_export_article", "Can export articles")
    create_permission_if_not_exists(SousArticle, "can_export_sousarticle", "Can export sub-articles")

    # Billing Models
    create_permission_if_not_exists(Facture, "can_export_facture", "Can export invoices")
    create_permission_if_not_exists(FactureGroupage, "can_export_facturegroupage", "Can export groupage invoices")
    create_permission_if_not_exists(FactureLibre, "can_export_facturelibre", "Can export free invoices")
    create_permission_if_not_exists(FactureAvoire, "can_export_factureavoire", "Can export credit notes")
    create_permission_if_not_exists(FactureAvoireGroupage, "can_export_factureavoiregroupage", "Can export groupage credit notes")
    create_permission_if_not_exists(FactureComplementaire, "can_export_facturecomplementaire", "Can export complementary invoices")
    create_permission_if_not_exists(FactureComplementaireGroupage, "can_export_facturecomplementairegroupage", "Can export groupage complementary invoices")
    create_permission_if_not_exists(Proforma, "can_export_proforma", "Can export proforma invoices")
    create_permission_if_not_exists(ProformaGroupage, "can_export_proformagroupage", "Can export groupage proformas")
    create_permission_if_not_exists(Paiement, "can_export_paiement", "Can export payments")
    create_permission_if_not_exists(PaiementGroupage, "can_export_paiementgroupage", "Can export groupage payments")
    create_permission_if_not_exists(PaiementFactureLibre, "can_export_paiementfacturelibre", "Can export free invoice payments")
    create_permission_if_not_exists(PaiementFactureComplementaire, "can_export_paiementfacturecomplementaire", "Can export complementary invoice payments")
    create_permission_if_not_exists(BonSortie, "can_export_bonsortie", "Can export exit permits")
    create_permission_if_not_exists(BonSortieGroupage, "can_export_bonsortiegroupage", "Can export groupage exit permits")
    create_permission_if_not_exists(BonSortieItem, "can_export_bonsortieitem", "Can export exit permit items")
    create_permission_if_not_exists(LignePrestation, "can_export_ligneprestation", "Can export service lines")
    create_permission_if_not_exists(LignePrestationArticle, "can_export_ligneprestationarticle", "Can export article service lines")
    create_permission_if_not_exists(LigneFactureLibre, "can_export_lignefacturelibre", "Can export free invoice lines")
    create_permission_if_not_exists(LigneProformaGroupage, "can_export_ligneproformagroupage", "Can export groupage proforma lines")
    create_permission_if_not_exists(LigneFactureComplementaireGroupage, "can_export_lignefacturecomplementairegroupage", "Can export groupage complementary invoice lines")
    create_permission_if_not_exists(Groupe, "can_export_groupe", "Can export groups")
    create_permission_if_not_exists(GroupeLigne, "can_export_groupeligne", "Can export group lines")
    create_permission_if_not_exists(FactureLibrePrefix, "can_export_facturelibreprefixes", "Can export free invoice prefixes")

    # Bareme Models
    create_permission_if_not_exists(Bareme, "can_export_bareme", "Can export pricing scales")
    create_permission_if_not_exists(Rubrique, "can_export_rubrique", "Can export pricing items")
    create_permission_if_not_exists(Prestation, "can_export_prestation", "Can export services")
    create_permission_if_not_exists(PrestationOccasionnelle, "can_export_prestationoccasionnelle", "Can export occasional services")
    create_permission_if_not_exists(PrestationOccasionnelleGroupage, "can_export_prestationoccasionnellegroupage", "Can export groupage occasional services")
    create_permission_if_not_exists(PrestationArticle, "can_export_prestationarticle", "Can export article services")
    create_permission_if_not_exists(Sejour, "can_export_sejour", "Can export stays")
    create_permission_if_not_exists(SejourTcGroupage, "can_export_sejourtcgroupage", "Can export groupage stays")
    create_permission_if_not_exists(SejourSousArticleGroupage, "can_export_sejoursousarticlegroupage", "Can export groupage article stays")
    create_permission_if_not_exists(Branchement, "can_export_branchement", "Can export connections")
    create_permission_if_not_exists(PrestationGroupage, "can_export_prestationgroupage", "Can export groupage services")
    create_permission_if_not_exists(PrestationVisiteGroupage, "can_export_prestationvisitegroupage", "Can export groupage visit services")

    # Groupage Models
    create_permission_if_not_exists(VisiteGroupage, "can_export_visitegroupage", "Can export groupage visits")
    create_permission_if_not_exists(PositionGroupage, "can_export_positiongroupage", "Can export groupage positions")

    # Reference Models
    create_permission_if_not_exists(Client, "can_export_client", "Can export clients")
    create_permission_if_not_exists(Transitaire, "can_export_transitaire", "Can export freight forwarders")
    create_permission_if_not_exists(AgentDouane, "can_export_agentdouane", "Can export customs agents")
    create_permission_if_not_exists(Parc, "can_export_parc", "Can export yards")
    create_permission_if_not_exists(Zone, "can_export_zone", "Can export zones")
    create_permission_if_not_exists(Banque, "can_export_banque", "Can export banks")
    create_permission_if_not_exists(Direction, "can_export_direction", "Can export directions")

def register_model_permissions():
    """Add export permissions to model Meta classes"""
    
    # This function is called to ensure the permissions are added to the model Meta
    # Django will handle the creation of these permissions during migration
    
    # The permissions are defined in the model Meta classes
    # See the models.py files for each app where we've added:
    # class Meta:
    #     permissions = [
    #         ("can_export_modelname", "Can export model verbose name plural"),
    #     ]
    pass
